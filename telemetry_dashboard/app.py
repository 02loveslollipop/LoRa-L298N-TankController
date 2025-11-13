"""Dash dashboard for real-time tank telemetry (excluding radar sweeps)."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

import dash
from dash import Dash, Input, Output, dcc, html, dash_table
import plotly.graph_objects as go
import redis
from redis import exceptions as redis_exceptions


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso8601(value: Optional[object]) -> str:
    if value is None:
        return utcnow().isoformat()
    if isinstance(value, (int, float)):
        seconds = value / 1000.0 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    if isinstance(value, str):
        txt = value.replace("Z", "+00:00") if value.endswith("Z") else value
        try:
            return datetime.fromisoformat(txt).astimezone(timezone.utc).isoformat()
        except ValueError:
            return utcnow().isoformat()
    return utcnow().isoformat()


def to_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class TelemetryCollector:
    """Background thread that tails the Redis telemetry stream."""

    def __init__(self, redis_url: str, stream: str, history_limit: int = 600) -> None:
        self.redis_url = redis_url
        self.stream = stream
        self.history_limit = history_limit
        self._history: Deque[Dict[str, object]] = deque(maxlen=history_limit)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._last_id = "$"
        self._client: Optional[redis.Redis] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        self._client = self._connect()
        self._prime_history()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _connect(self) -> redis.Redis:
        return redis.from_url(
            self.redis_url,
            decode_responses=True,
            health_check_interval=30,
            socket_keepalive=True,
        )

    def _prime_history(self) -> None:
        if not self._client:
            return
        try:
            rows = self._client.xrevrange(self.stream, count=self.history_limit)
        except redis_exceptions.RedisError as exc:
            print(f"[DASH] Failed to seed telemetry history: {exc}")
            return

        for message_id, fields in reversed(rows):
            parsed = self._parse_message(message_id, fields)
            if parsed:
                self._history.append(parsed)
        if rows:
            self._last_id = rows[0][0]

    def _loop(self) -> None:
        while self._running.is_set():
            if not self._client:
                time.sleep(1.0)
                self._client = self._connect()
                continue
            try:
                response = self._client.xread(
                    {self.stream: self._last_id},
                    block=5000,
                    count=100,
                )
            except redis_exceptions.ConnectionError as exc:
                print(f"[DASH] Redis connection lost: {exc}. Reconnecting…")
                time.sleep(1.0)
                try:
                    if self._client:
                        self._client.close()
                except Exception:
                    pass
                self._client = self._connect()
                continue
            except redis_exceptions.RedisError as exc:
                print(f"[DASH] Redis error while reading telemetry: {exc}")
                time.sleep(2.0)
                continue

            if not response:
                continue

            for _, messages in response:
                for message_id, fields in messages:
                    self._last_id = message_id
                    parsed = self._parse_message(message_id, fields)
                    if not parsed:
                        continue
                    with self._lock:
                        self._history.append(parsed)

    def snapshot(self) -> List[Dict[str, object]]:
        with self._lock:
            return [dict(item) for item in self._history]

    def _parse_message(self, message_id: str, fields: Dict[str, str]) -> Optional[Dict[str, object]]:
        payload_raw = fields.get("payload")
        if not payload_raw:
            return None
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError:
            payload = {}

        if payload.get("type") == "radar":
            # Skip radar payloads; the dashboard focuses on telemetry only.
            return None

        tank_id = fields.get("tankId") or payload.get("tankId") or "unknown"
        timestamp = fields.get("receivedAt") or payload.get("timestamp") or payload.get("timestamp_ms")
        timestamp_iso = to_iso8601(timestamp)

        environment = payload.get("environment") or {}
        gps = payload.get("gps") or {}
        sensors = payload.get("sensors") or {}
        battery = payload.get("battery") or {}

        record = {
            "id": message_id,
            "tankId": tank_id,
            "timestamp": timestamp_iso,
            "temperature_c": to_float(environment.get("temperature_c")),
            "humidity_pct": to_float(environment.get("humidity_pct")),
            "speed_mps": to_float(gps.get("speed_mps") or payload.get("speed_mps")),
            "hdop": to_float(gps.get("hdop")),
            "satellites": gps.get("satellites"),
            "lat": to_float(gps.get("lat")),
            "lon": to_float(gps.get("lon")),
            "battery_pct": to_float(
                payload.get("battery_pct")
                or sensors.get("battery_pct")
                or battery.get("percent")
            ),
            "battery_v": to_float(
                payload.get("battery_v")
                or sensors.get("battery_v")
                or battery.get("voltage")
            ),
        }
        return record


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_STATUS_STREAM = os.getenv("REDIS_STATUS_STREAM", "tank_status")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "600"))
REFRESH_INTERVAL_MS = int(os.getenv("REFRESH_INTERVAL_MS", "3000"))

collector = TelemetryCollector(REDIS_URL, REDIS_STATUS_STREAM, HISTORY_LIMIT)
collector.start()


# -----------------------------------------------------------------------------
# Dash App Setup
# -----------------------------------------------------------------------------
app: Dash = dash.Dash(__name__, title="Tank Telemetry Dashboard")
server = app.server


def metric_card(label: str, value: str, sub: Optional[str] = None) -> html.Div:
    return html.Div(
        [
            html.span(label, className="metric-label"),
            html.strong(value, className="metric-value"),
            html.span(sub or "", className="metric-sub"),
        ],
        className="metric-card",
    )


def build_line_chart(data: List[Dict[str, object]], key: str, title: str, yaxis: str) -> go.Figure:
    fig = go.Figure()
    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in data:
        value = row.get(key)
        timestamp = row.get("timestamp")
        if value is None or timestamp is None:
            continue
        grouped[str(row.get("tankId", "unknown"))].append(row)

    if not grouped:
        fig.update_layout(
            title=f"{title} (awaiting data)",
            xaxis_title="Timestamp",
            yaxis_title=yaxis,
            template="plotly_dark",
        )
        return fig

    for tank_id, rows in grouped.items():
        rows = sorted(rows, key=lambda item: item["timestamp"])
        fig.add_trace(
            go.Scatter(
                x=[r["timestamp"] for r in rows],
                y=[r[key] for r in rows],
                mode="lines+markers",
                name=tank_id,
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Timestamp",
        yaxis_title=yaxis,
        template="plotly_dark",
        legend_title="Tank",
        hovermode="x unified",
    )
    return fig


def build_map(data: List[Dict[str, object]]) -> go.Figure:
    points = [row for row in data if row.get("lat") is not None and row.get("lon") is not None]
    fig = go.Figure()
    if not points:
        fig.update_layout(
            title="GPS Track (awaiting data)",
            template="plotly_dark",
            margin=dict(l=0, r=0, t=40, b=0),
        )
        return fig

    grouped: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for row in points:
        grouped[str(row.get("tankId", "unknown"))].append(row)

    center = points[-1]
    for tank_id, rows in grouped.items():
        rows = sorted(rows, key=lambda item: item["timestamp"])
        fig.add_trace(
            go.Scattermapbox(
                lat=[r["lat"] for r in rows],
                lon=[r["lon"] for r in rows],
                mode="markers+lines",
                name=tank_id,
                marker={"size": 9},
                text=[f"{tank_id}<br>{r['timestamp']}" for r in rows],
                hoverinfo="text",
            )
        )

    fig.update_layout(
        title="GPS Track",
        mapbox_style="open-street-map",
        mapbox_zoom=14,
        mapbox_center={"lat": center["lat"], "lon": center["lon"]},
        margin=dict(l=0, r=0, t=40, b=0),
        template="plotly_dark",
    )
    return fig


def latest_summary(data: List[Dict[str, object]]) -> List[html.Div]:
    if not data:
        return [
            metric_card("Status", "Awaiting telemetry", "No samples received yet"),
        ]
    latest = data[-1]

    def pretty(value: Optional[float], suffix: str = "", precision: int = 1) -> str:
        if value is None:
            return "N/A"
        return f"{value:.{precision}f}{suffix}"

    cards = [
        metric_card("Tank", str(latest.get("tankId", "unknown")), latest.get("timestamp", "")),
        metric_card("Temperature", pretty(latest.get("temperature_c"), " C"), "Env sensor"),
        metric_card("Humidity", pretty(latest.get("humidity_pct"), "%"), "Env sensor"),
        metric_card("Speed", pretty(latest.get("speed_mps"), " m/s"), "GPS derived"),
        metric_card("Satellites", str(latest.get("satellites") or "—"), "GPS lock"),
        metric_card("Battery", pretty(latest.get("battery_pct"), "%"), pretty(latest.get("battery_v"), " V")),
    ]
    return cards


def build_table_rows(data: List[Dict[str, object]]) -> List[Dict[str, object]]:
    rows = data[-100:]
    result: List[Dict[str, object]] = []
    for row in reversed(rows):
        result.append(
            {
                "tankId": row.get("tankId"),
                "timestamp": row.get("timestamp"),
                "temperature_c": row.get("temperature_c"),
                "humidity_pct": row.get("humidity_pct"),
                "speed_mps": row.get("speed_mps"),
                "hdop": row.get("hdop"),
                "satellites": row.get("satellites"),
                "battery_pct": row.get("battery_pct"),
            }
        )
    return result


TABLE_COLUMNS = [
    {"name": "Tank", "id": "tankId"},
    {"name": "Timestamp", "id": "timestamp"},
    {"name": "Temp (C)", "id": "temperature_c", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "Humidity (%)", "id": "humidity_pct", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "Speed (m/s)", "id": "speed_mps", "type": "numeric", "format": {"specifier": ".2f"}},
    {"name": "HDOP", "id": "hdop", "type": "numeric", "format": {"specifier": ".1f"}},
    {"name": "Satellites", "id": "satellites", "type": "numeric"},
    {"name": "Battery (%)", "id": "battery_pct", "type": "numeric", "format": {"specifier": ".1f"}},
]


app.layout = html.Div(
    [
        html.Header(
            [
                html.H1("Tank Telemetry Dashboard"),
                html.Span(id="last-update", className="muted"),
            ]
        ),
        html.Div(id="summary-cards", className="metric-grid"),
        html.Div(
            [
                dcc.Graph(id="temperature-chart"),
                dcc.Graph(id="humidity-chart"),
            ],
            className="chart-grid",
        ),
        html.Div(
            [
                dcc.Graph(id="speed-chart"),
                dcc.Graph(id="gps-chart"),
            ],
            className="chart-grid",
        ),
        html.Div(
            [
                dcc.Graph(id="battery-chart"),
                dcc.Graph(id="hdop-chart"),
            ],
            className="chart-grid",
        ),
        html.Div(
            [
                html.H3("Recent Telemetry Samples"),
                dash_table.DataTable(
                    id="telemetry-table",
                    columns=TABLE_COLUMNS,
                    data=[],
                    page_size=10,
                    style_header={
                        "backgroundColor": "#0f172a",
                        "color": "#e2e8f0",
                        "fontWeight": "600",
                    },
                    style_data={
                        "backgroundColor": "rgba(15,23,42,0.6)",
                        "color": "#e2e8f0",
                        "border": "0px",
                    },
                    style_table={"overflowX": "auto"},
                    sort_action="native",
                    filter_action="native",
                ),
            ],
            className="table-card",
        ),
        dcc.Interval(id="poll-interval", interval=REFRESH_INTERVAL_MS, n_intervals=0),
        html.Footer("Data source: Redis stream populated by the control broker."),
    ],
    className="page",
)


@app.callback(
    Output("summary-cards", "children"),
    Output("temperature-chart", "figure"),
    Output("humidity-chart", "figure"),
    Output("speed-chart", "figure"),
    Output("gps-chart", "figure"),
    Output("battery-chart", "figure"),
    Output("hdop-chart", "figure"),
    Output("telemetry-table", "data"),
    Output("last-update", "children"),
    Input("poll-interval", "n_intervals"),
)
def refresh_dashboard(_: int):
    data = collector.snapshot()
    summary = latest_summary(data)
    temperature_fig = build_line_chart(data, "temperature_c", "Temperature", "C")
    humidity_fig = build_line_chart(data, "humidity_pct", "Humidity", "%")
    speed_fig = build_line_chart(data, "speed_mps", "Speed", "m/s")
    gps_fig = build_map(data)
    battery_fig = build_line_chart(data, "battery_pct", "Battery", "%")
    hdop_fig = build_line_chart(data, "hdop", "HDOP", "unitless")
    table_data = build_table_rows(data)
    last_message = f"Last update: {data[-1]['timestamp']}" if data else "Awaiting telemetry…"
    return summary, temperature_fig, humidity_fig, speed_fig, gps_fig, battery_fig, hdop_fig, table_data, last_message


# Simple styles embedded to avoid a separate assets directory.
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
        body {
            font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background-color: #020617;
            color: #e2e8f0;
            margin: 0;
            padding: 0 1.5rem 2rem;
        }
        .page {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            padding: 1.5rem 0;
        }
        .muted {
            color: rgba(226, 232, 240, 0.65);
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .metric-card {
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 12px;
            padding: 0.9rem 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.3rem;
        }
        .metric-label {
            font-size: 0.9rem;
            color: rgba(148, 163, 184, 0.95);
        }
        .metric-value {
            font-size: 1.4rem;
        }
        .metric-sub {
            font-size: 0.8rem;
            color: rgba(148, 163, 184, 0.75);
        }
        .chart-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .table-card {
            background: rgba(15,23,42,0.9);
            border: 1px solid rgba(59,130,246,0.2);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }
        .table-card h3 {
            margin-top: 0;
            margin-bottom: 0.75rem;
        }
        footer {
            font-size: 0.8rem;
            color: rgba(148,163,184,0.8);
            text-align: right;
        }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


if __name__ == "__main__":
    app.run_server(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=False)
