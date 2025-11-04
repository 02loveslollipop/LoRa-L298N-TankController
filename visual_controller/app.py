import asyncio
import json
import os
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import httpx
import redis.asyncio as redis
import httpx
from redis import exceptions as redis_exceptions
from redis.backoff import ExponentialBackoff
from redis.asyncio.retry import Retry
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, validator
from starlette.websockets import WebSocketState


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CommandPayload(BaseModel):
    command: str
    leftSpeed: Optional[int] = None
    rightSpeed: Optional[int] = None
    sequence: Optional[int] = None
    timestamp: Optional[str] = None

    @validator("command")
    def validate_command(cls, value: str) -> str:
        allowed = {"forward", "backward", "left", "right", "stop", "setspeed"}
        value_lower = value.lower()
        if value_lower not in allowed:
            raise ValueError(f"Unsupported command '{value}'.")
        return value_lower

    @validator("leftSpeed", "rightSpeed")
    def validate_speed(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        if not 0 <= value <= 255:
            raise ValueError("Speed must be between 0 and 255.")
        return value


# Redis configuration -------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_COMMAND_STREAM = os.getenv("REDIS_COMMAND_STREAM", "tank_commands")
REDIS_STATUS_STREAM = os.getenv("REDIS_STATUS_STREAM", "tank_status")
REDIS_COMMAND_MAXLEN = int(os.getenv("REDIS_COMMAND_MAXLEN", "500"))
REDIS_STATUS_START = os.getenv("REDIS_STATUS_STREAM_START", "0-0")
REDIS_RADAR_STREAM = os.getenv("REDIS_RADAR_STREAM", "tank_radar")
REDIS_RADAR_START = os.getenv("REDIS_RADAR_STREAM_START", "0-0")
CONTROL_BROKER_URL = os.getenv("CONTROL_BROKER_URL", "http://control-broker").rstrip("/")
CONTROL_BROKER_TIMEOUT = float(os.getenv("CONTROL_BROKER_TIMEOUT", "5.0"))


# Application setup ---------------------------------------------------
app = FastAPI(title="Tank Visual Controller", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Runtime state -------------------------------------------------------
subscribers: Dict[str, Set[WebSocket]] = defaultdict(set)
latest_status: Dict[str, dict] = {}
latest_radar: Dict[str, dict] = {}
subscriber_lock = asyncio.Lock()
redis_client_lock = asyncio.Lock()


def _build_connection_kwargs() -> dict:
    kwargs = {
        "decode_responses": True,
        "retry": Retry(
            ExponentialBackoff(cap=1),
            retries=5,
            supported_errors=(redis_exceptions.ConnectionError,),
        ),
        "health_check_interval": 30,
        "socket_keepalive": True,
        "retry_on_timeout": True,
    }
    if REDIS_URL.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = None
        kwargs["ssl_check_hostname"] = False
    return kwargs


async def _create_redis_client() -> redis.Redis:
    client = redis.from_url(REDIS_URL, **_build_connection_kwargs())
    try:
        await client.ping()
    except Exception:
        await client.close()
        raise
    return client


async def reset_redis_client() -> redis.Redis:
    async with redis_client_lock:
        existing = getattr(app.state, "redis", None)
        if existing is not None:
            app.state.redis = None
            await existing.close()
        new_client = await _create_redis_client()
        app.state.redis = new_client
        return new_client


async def get_redis_client() -> redis.Redis:
    client = getattr(app.state, "redis", None)
    if client is None:
        return await reset_redis_client()
    return client


async def fetch_broker_tanks() -> Optional[List[dict]]:
    """Retrieve tank snapshot from the control broker service."""
    if not CONTROL_BROKER_URL:
        return None
    url = f"{CONTROL_BROKER_URL}/tanks"
    try:
        async with httpx.AsyncClient(timeout=CONTROL_BROKER_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        print(f"[VISUAL] Control broker /tanks returned {exc.response.status_code}: {exc}")
        return None
    except httpx.HTTPError as exc:
        print(f"[VISUAL] Control broker unreachable: {exc}")
        return None
    except ValueError as exc:
        print(f"[VISUAL] Control broker returned invalid JSON: {exc}")
        return None

    if isinstance(payload, list):
        return payload
    print(f"[VISUAL] Unexpected control broker payload type: {type(payload)}")
    return None


async def register_subscriber(tank_id: str, websocket: WebSocket) -> None:
    await websocket.accept()
    async with subscriber_lock:
        subscribers[tank_id].add(websocket)
        telemetry_snapshot = latest_status.get(tank_id)
        radar_snapshot = latest_radar.get(tank_id)
    if telemetry_snapshot:
        await safe_send(websocket, telemetry_snapshot)
    if radar_snapshot:
        await safe_send(websocket, radar_snapshot)


async def unregister_subscriber(tank_id: str, websocket: WebSocket) -> None:
    async with subscriber_lock:
        bucket = subscribers.get(tank_id)
        if not bucket:
            return
        bucket.discard(websocket)
        if not bucket:
            subscribers.pop(tank_id, None)


async def broadcast_status(tank_id: str, message: dict) -> None:
    async with subscriber_lock:
        sockets = list(subscribers.get(tank_id, []))
    if not sockets:
        return

    for ws in sockets:
        if ws.application_state == WebSocketState.CONNECTED:
            await safe_send(ws, message)
        else:
            await unregister_subscriber(tank_id, ws)


async def safe_send(websocket: WebSocket, message: dict) -> None:
    try:
        await websocket.send_text(json.dumps(message))
    except Exception:
        pass


async def append_command(tank_id: str, payload: CommandPayload) -> None:
    data = payload.dict(exclude_none=True)
    data["tankId"] = tank_id
    data.setdefault("timestamp", utcnow().isoformat())
    last_error: Optional[redis_exceptions.RedisError] = None
    for attempt in range(2):
        redis_client = await get_redis_client()
        try:
            await redis_client.xadd(
                REDIS_COMMAND_STREAM,
                data,
                maxlen=REDIS_COMMAND_MAXLEN,
                approximate=True,
            )
            return
        except redis_exceptions.ConnectionError as exc:
            last_error = exc
            print(f"[VISUAL] Redis connection lost while enqueuing {tank_id}: {exc}")
            await reset_redis_client()
        except redis_exceptions.RedisError as exc:
            last_error = exc
            print(f"[VISUAL] Failed to enqueue command for {tank_id}: {exc}")
            break
    if last_error:
        raise last_error


async def status_listener() -> None:
    last_id = REDIS_STATUS_START
    print(
        f"[VISUAL] Status listener watching stream '{REDIS_STATUS_STREAM}' starting at '{last_id}'"
    )

    while True:
        try:
            redis_client = await get_redis_client()
            results = await redis_client.xread(
                streams={REDIS_STATUS_STREAM: last_id},
                count=50,
                block=5000,
            )

            if not results:
                continue

            for _, messages in results:
                for message_id, raw in messages:
                    last_id = message_id
                    tank_id = raw.get("tankId")
                    if not tank_id:
                        continue

                    payload_data = raw.get("payload")
                    try:
                        payload = json.loads(payload_data) if payload_data else {}
                    except json.JSONDecodeError:
                        payload = {"raw": payload_data}

                    received_at = raw.get("receivedAt", utcnow().isoformat())
                    message = {
                        "type": "telemetry",
                        "tankId": tank_id,
                        "payload": payload,
                        "receivedAt": received_at,
                        "id": message_id,
                    }
                    latest_status[tank_id] = message
                    await broadcast_status(tank_id, message)
        except asyncio.CancelledError:
            print("[VISUAL] Status listener cancelled")
            break
        except redis_exceptions.ConnectionError as exc:
            print(f"[VISUAL] Status listener redis connection lost: {exc}")
            await reset_redis_client()
            await asyncio.sleep(0.5)
        except Exception as exc:
            print(f"[VISUAL] Status listener error: {exc}")
            await asyncio.sleep(1.0)


async def radar_listener() -> None:
    last_id = REDIS_RADAR_START
    print(
        f"[VISUAL] Radar listener watching stream '{REDIS_RADAR_STREAM}' starting at '{last_id}'"
    )

    while True:
        try:
            redis_client = await get_redis_client()
            results = await redis_client.xread(
                streams={REDIS_RADAR_STREAM: last_id},
                count=50,
                block=5000,
            )

            if not results:
                continue

            for _, messages in results:
                for message_id, raw in messages:
                    last_id = message_id
                    payload_data = raw.get("payload")
                    try:
                        payload = json.loads(payload_data) if payload_data else {}
                    except json.JSONDecodeError:
                        payload = {"raw": payload_data}

                    source_id = raw.get("sourceId") or payload.get("sourceId")
                    if not source_id:
                        continue

                    received_at = raw.get("receivedAt", utcnow().isoformat())
                    message = {
                        "type": "radar",
                        "sourceId": source_id,
                        "payload": payload,
                        "receivedAt": received_at,
                        "id": message_id,
                    }
                    latest_radar[source_id] = message
                    await broadcast_status(source_id, message)
        except asyncio.CancelledError:
            print("[VISUAL] Radar listener cancelled")
            break
        except redis_exceptions.ConnectionError as exc:
            print(f"[VISUAL] Radar listener redis connection lost: {exc}")
            await reset_redis_client()
            await asyncio.sleep(0.5)
        except Exception as exc:
            print(f"[VISUAL] Radar listener error: {exc}")
            await asyncio.sleep(1.0)


@app.on_event("startup")
async def on_startup() -> None:
    await reset_redis_client()
    app.state.status_task = asyncio.create_task(status_listener())
    app.state.radar_task = asyncio.create_task(radar_listener())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "status_task", None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    radar_task = getattr(app.state, "radar_task", None)
    if radar_task:
        radar_task.cancel()
        with suppress(asyncio.CancelledError):
            await radar_task
    redis_client = getattr(app.state, "redis", None)
    if redis_client:
        await redis_client.close()
    app.state.redis = None


# API endpoints -------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": utcnow().isoformat(), "version": "1.0.0"}


@app.get("/tanks")
async def list_tanks() -> Dict[str, dict]:
    snapshot: Dict[str, dict] = {}
    for tank_id, status in latest_status.items():
        combined = dict(status)
        radar = latest_radar.get(tank_id)
        if radar:
            combined["radar"] = radar
        snapshot[tank_id] = combined
    for source_id, radar in latest_radar.items():
        snapshot.setdefault(source_id, {"radar": radar})
    broker_snapshot = await fetch_broker_tanks()
    if broker_snapshot:
        for entry in broker_snapshot:
            tank_id = entry.get("tankId")
            if not tank_id:
                continue
            bucket = snapshot.setdefault(tank_id, {})
            bucket["connection"] = entry
    return snapshot


@app.post("/command/{tank_id}")
async def enqueue_command(tank_id: str, payload: CommandPayload) -> dict:
    try:
        await append_command(tank_id, payload)
    except redis_exceptions.RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    return {"status": "queued", "tankId": tank_id, "command": payload.dict(exclude_none=True)}


@app.post("/tanks/{tank_id}/reset")
async def request_tank_reset(tank_id: str) -> dict:
    if not CONTROL_BROKER_URL:
        raise HTTPException(status_code=503, detail="Control broker URL not configured")
    url = f"{CONTROL_BROKER_URL}/tanks/{tank_id}/reset"
    try:
        async with httpx.AsyncClient(timeout=CONTROL_BROKER_TIMEOUT) as client:
            response = await client.post(url)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Control broker unreachable") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code == 404:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        raise HTTPException(status_code=404, detail=detail or "Tank not found")
    if response.status_code >= 400:
        detail = payload.get("detail") if isinstance(payload, dict) else None
        raise HTTPException(status_code=502, detail=detail or "Control broker error")

    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("tankId", tank_id)
    payload.setdefault("status", "reset")
    payload.setdefault("timestamp", utcnow().isoformat())
    return payload


@app.websocket("/ws/ui/{tank_id}")
async def ui_socket(websocket: WebSocket, tank_id: str) -> None:
    try:
        await register_subscriber(tank_id, websocket)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await unregister_subscriber(tank_id, websocket)
    except Exception as exc:
        await unregister_subscriber(tank_id, websocket)
        print(f"[VISUAL] WebSocket error for tank {tank_id}: {exc}")


CONTROLLER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Tank Controller - {{tank_id}}</title>
    <style>
      body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #f4f6fb; margin: 0; padding: 2.5rem; }
      h1 { margin-bottom: 0.25rem; font-size: 2rem; }
      h2 { margin: 0 0 0.75rem 0; font-size: 1.25rem; }
      button { padding: 0.75rem 1.5rem; margin: 0.5rem; font-size: 1.05rem; background: #1f6feb; border: none; border-radius: 6px; color: white; cursor: pointer; transition: background 0.2s ease; }
      button:hover { background: #2d7ff9; }
      button:disabled { background: #3a3f47; cursor: not-allowed; }
      .layout { display: flex; flex-wrap: wrap; gap: 2rem; margin-top: 1.5rem; }
      .panel { background: #121826; border-radius: 12px; padding: 1.5rem; box-shadow: 0 12px 28px rgba(1, 4, 9, 0.35); flex: 1 1 320px; min-width: 280px; }
      .panel h2 { color: #57a6ff; }
      #log { background: #0b0e14; border-radius: 10px; padding: 1rem; margin-top: 1.5rem; max-height: 18rem; overflow-y: auto; font-family: monospace; border: 1px solid #1f2633; }
      .grid { display: grid; grid-template-columns: repeat(3, minmax(120px, 1fr)); gap: 1rem; margin-top: 1rem; }
      label { display: block; margin-top: 1.5rem; }
      #statusView { margin-top: 1rem; background: #0b0e14; border-radius: 10px; padding: 1rem; white-space: pre-wrap; font-family: monospace; border: 1px solid #1f2633; }
      #radarCanvas { width: 100%; max-width: 360px; height: auto; display: block; margin: 0 auto; background: #020b1b; border-radius: 50%; }
      #radarSummary { margin-top: 0.75rem; font-family: monospace; text-align: center; opacity: 0.85; }
      .tab-header { display: flex; gap: 0.75rem; margin-top: 0.75rem; margin-bottom: 1.25rem; }
      .tab-button { flex: 1; padding: 0.75rem 1rem; background: #161b26; border: 1px solid #2d3547; border-radius: 8px; color: #9fb7ff; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }
      .tab-button:hover { border-color: #3c4c6a; color: #d7e4ff; }
      .tab-button.active { background: #1f6feb; color: #ffffff; border-color: #1f6feb; box-shadow: 0 8px 22px rgba(31, 111, 235, 0.35); }
      .tab-content { display: none; }
      .tab-content.active { display: block; }
      .nt-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1rem; margin-top: 1.25rem; }
      .nt-card { background: #0b0e14; border: 1px solid #1f2633; border-radius: 10px; padding: 1rem; font-size: 0.95rem; color: #d5dcf5; }
      .nt-card strong { display: block; font-size: 0.95rem; margin-bottom: 0.5rem; color: #57a6ff; }
      .nt-hint { margin-top: 1rem; font-size: 0.9rem; color: #8fa0c3; opacity: 0.9; }
      kbd { display: inline-block; padding: 0.35rem 0.6rem; border-radius: 6px; border: 1px solid #2d3547; background: #111726; color: #dbe5ff; box-shadow: inset 0 -2px 0 rgba(0, 0, 0, 0.35); font-size: 0.95rem; }
      .status-badge { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.45rem 0.9rem; border-radius: 999px; background: rgba(31, 111, 235, 0.15); border: 1px solid rgba(31, 111, 235, 0.4); color: #cfe1ff; font-size: 0.9rem; margin-right: 0.5rem; }
      .status-badge.offline { background: rgba(216, 59, 125, 0.15); border-color: rgba(216, 59, 125, 0.4); color: #ffcfe4; }
      .tank-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-top: 0.75rem; flex-wrap: wrap; }
      .tank-list { list-style: none; padding: 0; margin: 1.25rem 0 0; display: flex; flex-direction: column; gap: 0.75rem; }
      .tank-item { display: flex; align-items: center; justify-content: space-between; gap: 1rem; background: #0b0e14; border: 1px solid #1f2633; border-radius: 10px; padding: 0.85rem 1rem; transition: border 0.2s ease, box-shadow 0.2s ease; }
      .tank-item.current { border-color: rgba(31, 111, 235, 0.8); box-shadow: 0 0 0 1px rgba(31, 111, 235, 0.35); }
      .tank-meta { display: flex; flex-direction: column; gap: 0.35rem; }
      .tank-id { font-weight: 600; color: #e1e8ff; font-size: 1rem; }
      .tank-status { font-size: 0.85rem; color: #8fa0c3; opacity: 0.9; }
      .tank-actions { display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap; }
      .tank-actions button { margin: 0; }
      .reset-btn { background: #d83b7d; }
      .reset-btn:hover { background: #f0559b; }
      .refresh-btn { background: #2d7ff9; margin: 0; }
      .tank-empty { color: #8fa0c3; font-size: 0.95rem; margin-top: 1.25rem; text-align: center; }
      .tank-updated { font-size: 0.85rem; color: #8fa0c3; }
    </style>
</head>
<body>
  <h1>Tank Controller - {{tank_id}}</h1>
  <p>Status: <span id="status">Connecting...</span></p>
  <div class="layout">
    <section class="panel">
      <h2>Controller Modes</h2>
      <div class="tab-header">
        <button class="tab-button active" data-target="legacy-controller">Legacy Controller</button>
        <button class="tab-button" data-target="nt-controller">NT Controller</button>
      </div>
      <div class="tab-content active" id="legacy-controller">
        <div class="grid">
          <button data-command="forward">Forward</button>
          <button data-command="stop">Stop</button>
          <button data-command="backward">Backward</button>
          <button data-command="left">Left</button>
          <button data-command="right">Right</button>
        </div>
        <label>Speed:
          <input type="range" id="speed" min="0" max="255" value="180" />
          <span id="speedValue">180</span>
        </label>
      </div>
      <div class="tab-content" id="nt-controller">
        <p>Use your keyboard to drive the tank. Hold the keys to keep moving.</p>
        <div>
          <span class="status-badge">Mode: <span id="ntMode">Stopped</span></span>
          <span class="status-badge">Speed: <span id="ntSpeed">0</span></span>
        </div>
        <div class="nt-grid">
          <div class="nt-card">
            <strong>Throttle</strong>
            <p><kbd>W</kbd> accelerate forward<br /><kbd>S</kbd> accelerate reverse</p>
          </div>
          <div class="nt-card">
            <strong>Turning</strong>
            <p><kbd>A</kbd> turn left<br /><kbd>D</kbd> turn right</p>
          </div>
          <div class="nt-card">
            <strong>Brake</strong>
            <p><kbd>Space</kbd> immediate stop</p>
          </div>
        </div>
        <p class="nt-hint">Keyboard control is active while the NT tab is selected.</p>
      </div>
      <div id="statusView"></div>
    </section>
      <section class="panel">
        <h2>Radar Telemetry</h2>
        <canvas id="radarCanvas" width="360" height="360"></canvas>
        <div id="radarSummary">Awaiting radar telemetry...</div>
      </section>
      <section class="panel">
        <h2>Tank Status</h2>
        <p class="nt-hint">Monitor connected tanks and trigger remote resets when a unit becomes unresponsive.</p>
        <div class="tank-toolbar">
          <button id="refreshTanks" class="refresh-btn">Refresh List</button>
          <span id="tankRefreshStatus" class="tank-updated"></span>
        </div>
        <ul id="tankList" class="tank-list"></ul>
      </section>
    </div>
    <div id="log"></div>
    <script>
      const tankId = "{{tank_id}}";
      const status = document.getElementById("status");
      const log = document.getElementById("log");
      const statusView = document.getElementById("statusView");
      const speedSlider = document.getElementById("speed");
      const speedValue = document.getElementById("speedValue");
      const radarCanvas = document.getElementById("radarCanvas");
      const radarSummary = document.getElementById("radarSummary");
      const radarCtx = radarCanvas.getContext("2d");
      const tabButtons = document.querySelectorAll(".tab-button");
      const tabPanels = document.querySelectorAll(".tab-content");
      const tankListEl = document.getElementById("tankList");
      const refreshTanksBtn = document.getElementById("refreshTanks");
      const tankRefreshStatus = document.getElementById("tankRefreshStatus");
      const ntMode = document.getElementById("ntMode");
      const ntSpeed = document.getElementById("ntSpeed");
      const legacyPanelId = "legacy-controller";
      const ntPanelId = "nt-controller";
      const activeTankId = tankId;
      const TANK_REFRESH_INTERVAL_MS = 30000;
      const apiBase = window.location.origin;
      const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${wsProtocol}://${window.location.host}/ws/ui/${tankId}`);
      let tankRefreshHandle = null;

      const NT_SPEED_STEP = 25;
      const DEFAULT_TURN_SPEED = 160;
      const MAX_SPEED = 255;

      const ntState = {
        direction: "stopped",
        speed: 0,
        turn: null,
      };

      let ntActive = false;

      if (speedSlider && speedValue) {
        speedSlider.addEventListener("input", () => {
          speedValue.textContent = speedSlider.value;
        });
      }

      function write(message) {
        const el = document.createElement("div");
        el.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
        log.prepend(el);
      }

      function renderStatus(data) {
        statusView.textContent = JSON.stringify(data, null, 2);
      }

      function formatRelativeTime(isoValue, fallbackSeconds) {
        if (Number.isFinite(fallbackSeconds) && fallbackSeconds >= 0) {
          if (fallbackSeconds < 5) return "moments ago";
          if (fallbackSeconds < 60) return `${Math.round(fallbackSeconds)}s ago`;
          if (fallbackSeconds < 3600) return `${Math.round(fallbackSeconds / 60)}m ago`;
          return `${Math.round(fallbackSeconds / 3600)}h ago`;
        }
        if (!isoValue) {
          return "unknown";
        }
        const parsed = new Date(isoValue);
        if (Number.isNaN(parsed.getTime())) {
          return isoValue;
        }
        const diffSeconds = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 1000));
        if (diffSeconds < 5) return "moments ago";
        if (diffSeconds < 60) return `${diffSeconds}s ago`;
        if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
        return `${Math.floor(diffSeconds / 3600)}h ago`;
      }

      function renderTankList(snapshot) {
        if (!tankListEl) {
          return;
        }
        tankListEl.innerHTML = "";
        const entries = Object.entries(snapshot || {});
        if (!entries.length) {
          const empty = document.createElement("li");
          empty.className = "tank-empty";
          empty.textContent = "No tanks have reported yet.";
          tankListEl.appendChild(empty);
          return;
        }
        entries.sort(([a], [b]) => a.localeCompare(b));
        for (const [id, raw] of entries) {
          const entry = raw || {};
          const li = document.createElement("li");
          li.className = "tank-item";
          if (id === activeTankId) {
            li.classList.add("current");
          }

          const connection = entry.connection || {};
          const telemetry = entry.payload || {};
          const meta = document.createElement("div");
          meta.className = "tank-meta";

          const title = document.createElement("span");
          title.className = "tank-id";
          title.textContent = id;
          meta.appendChild(title);

          const info = document.createElement("span");
          info.className = "tank-status";
          const lastSeenSource = connection.lastSeen || entry.receivedAt || telemetry.timestamp;
          const activity = formatRelativeTime(lastSeenSource, connection.stale);
          const infoParts = [];
          if (typeof connection.commandsSent === "number") {
            infoParts.push(`Commands: ${connection.commandsSent}`);
          }
          if (activity) {
            infoParts.push(`Last seen: ${activity}`);
          }
          if (!infoParts.length) {
            infoParts.push("No telemetry recorded yet");
          }
          info.textContent = infoParts.join(" • ");
          meta.appendChild(info);

          const actions = document.createElement("div");
          actions.className = "tank-actions";

          const badge = document.createElement("span");
          badge.className = "status-badge";
          if (connection.connected === true) {
            badge.textContent = "Connected";
          } else if (connection.connected === false) {
            badge.classList.add("offline");
            badge.textContent = "Disconnected";
          } else {
            badge.textContent = "Unknown";
          }
          actions.appendChild(badge);

          const resetButton = document.createElement("button");
          resetButton.type = "button";
          resetButton.className = "reset-btn";
          resetButton.textContent = "Reset";
          resetButton.addEventListener("click", async () => {
            resetButton.disabled = true;
            try {
              await resetTank(id);
            } finally {
              resetButton.disabled = false;
            }
          });
          actions.appendChild(resetButton);

          li.appendChild(meta);
          li.appendChild(actions);
          tankListEl.appendChild(li);
        }
      }

      function cancelTankRefresh() {
        if (tankRefreshHandle) {
          clearInterval(tankRefreshHandle);
          tankRefreshHandle = null;
        }
      }

      function scheduleTankRefresh() {
        if (!tankListEl) {
          return;
        }
        cancelTankRefresh();
        tankRefreshHandle = setInterval(() => {
          loadTankList({ announce: false });
        }, TANK_REFRESH_INTERVAL_MS);
      }

      async function loadTankList(options = {}) {
        if (!tankListEl) {
          return;
        }
        const { announce = false } = options;
        if (refreshTanksBtn) {
          refreshTanksBtn.disabled = true;
        }
        try {
          const response = await fetch(`${apiBase}/tanks`, { cache: "no-store" });
          if (!response.ok) {
            throw new Error(response.statusText);
          }
          const snapshot = await response.json();
          renderTankList(snapshot);
          if (tankRefreshStatus) {
            tankRefreshStatus.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
          }
          if (announce) {
            write("Tank list refreshed.");
          }
        } catch (error) {
          if (tankRefreshStatus) {
            tankRefreshStatus.textContent = "Refresh failed";
          }
          console.error("Tank list refresh failed", error);
          if (announce) {
            write(`Failed to refresh tanks: ${error}`);
          }
        } finally {
          if (refreshTanksBtn) {
            refreshTanksBtn.disabled = false;
          }
        }
      }

      async function resetTank(targetTankId) {
        if (!targetTankId) {
          return;
        }
        try {
          if (tankRefreshStatus) {
            tankRefreshStatus.textContent = `Reset requested for ${targetTankId}...`;
          }
          const response = await fetch(`${apiBase}/tanks/${encodeURIComponent(targetTankId)}/reset`, {
            method: "POST",
          });
          let payload = {};
          try {
            payload = await response.json();
          } catch (parseError) {
            payload = {};
          }
          if (!response.ok) {
            const detail = payload && (payload.detail || payload.error);
            throw new Error(detail || response.statusText);
          }
          write(`Reset requested for ${targetTankId}`);
          await loadTankList({ announce: false });
        } catch (error) {
          console.error(`Reset request failed for ${targetTankId}`, error);
          write(`Reset failed for ${targetTankId}: ${error instanceof Error ? error.message : error}`);
        }
      }

      function clampSpeed(value) {
        return Math.max(0, Math.min(MAX_SPEED, Math.round(value)));
      }

      function updateNTIndicators() {
        if (ntMode) {
          const motion = ntState.turn
            ? (ntState.turn === "left" ? "Turning Left" : "Turning Right")
            : (ntState.direction === "forward"
              ? "Forward"
              : ntState.direction === "backward"
                ? "Reverse"
                : "Stopped");
          ntMode.textContent = motion;
        }
        if (ntSpeed) {
          ntSpeed.textContent = ntState.speed;
        }
      }
      updateNTIndicators();

      function activateTab(targetId) {
        tabButtons.forEach((btn) => {
          btn.classList.toggle("active", btn.dataset.target === targetId);
        });
        tabPanels.forEach((panel) => {
          panel.classList.toggle("active", panel.id === targetId);
        });
        if (targetId !== ntPanelId && ntState.turn) {
          finishTurn(ntState.turn);
        }
        ntActive = targetId === ntPanelId;
        updateNTIndicators();
      }

      tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => activateTab(btn.dataset.target));
      });
      activateTab(legacyPanelId);

      if (refreshTanksBtn) {
        refreshTanksBtn.addEventListener("click", () => loadTankList({ announce: true }));
      }
      if (tankListEl) {
        loadTankList({ announce: false });
        scheduleTankRefresh();
        document.addEventListener("visibilitychange", () => {
          if (document.hidden) {
            cancelTankRefresh();
          } else {
            loadTankList({ announce: false });
            scheduleTankRefresh();
          }
        });
        window.addEventListener("beforeunload", cancelTankRefresh);
      }

      function isTypingTarget(element) {
        if (!element) {
          return false;
        }
        if (element.isContentEditable) {
          return true;
        }
        const tag = element.tagName ? element.tagName.toUpperCase() : "";
        return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || tag === "BUTTON";
      }

      function applyBrake() {
        ntState.direction = "stopped";
        ntState.turn = null;
        ntState.speed = 0;
        updateNTIndicators();
        sendCommand("stop", { leftSpeed: 0, rightSpeed: 0 });
      }

      function accelerate(direction) {
        if (direction === "forward") {
          if (ntState.direction === "backward" && ntState.speed > 0) {
            sendCommand("stop", { leftSpeed: 0, rightSpeed: 0 });
            ntState.speed = 0;
          }
          ntState.direction = "forward";
        } else {
          if (ntState.direction === "forward" && ntState.speed > 0) {
            sendCommand("stop", { leftSpeed: 0, rightSpeed: 0 });
            ntState.speed = 0;
          }
          ntState.direction = "backward";
        }
        ntState.turn = null;
        ntState.speed = Math.max(NT_SPEED_STEP, clampSpeed(ntState.speed + NT_SPEED_STEP));
        const command = direction === "forward" ? "forward" : "backward";
        sendCommand(command, { leftSpeed: ntState.speed, rightSpeed: ntState.speed });
        updateNTIndicators();
      }

      function startTurn(direction) {
        const turn = direction === "left" ? "left" : "right";
        if (ntState.turn === turn) {
          return;
        }
        ntState.turn = turn;
        const baseSpeed = ntState.speed > 0 ? ntState.speed : DEFAULT_TURN_SPEED;
        ntState.speed = clampSpeed(baseSpeed);
        const command = turn === "left" ? "left" : "right";
        sendCommand(command, { leftSpeed: ntState.speed, rightSpeed: ntState.speed });
        updateNTIndicators();
      }

      function finishTurn(direction) {
        const turn = direction === "left" ? "left" : "right";
        if (ntState.turn !== turn) {
          return;
        }
        ntState.turn = null;
        if (ntState.direction === "forward" && ntState.speed > 0) {
          sendCommand("forward", { leftSpeed: ntState.speed, rightSpeed: ntState.speed });
        } else if (ntState.direction === "backward" && ntState.speed > 0) {
          sendCommand("backward", { leftSpeed: ntState.speed, rightSpeed: ntState.speed });
        } else {
          applyBrake();
          return;
        }
        updateNTIndicators();
      }

      function handleKeyDown(event) {
        if (!ntActive) {
          return;
        }
        if (isTypingTarget(event.target) || isTypingTarget(document.activeElement)) {
          return;
        }
        const key = event.code === "Space" ? " " : event.key.toLowerCase();
        if (!["w", "a", "s", "d", " "].includes(key)) {
          return;
        }
        event.preventDefault();
        switch (key) {
          case "w":
            accelerate("forward");
            break;
          case "s":
            accelerate("backward");
            break;
          case "a":
            startTurn("left");
            break;
          case "d":
            startTurn("right");
            break;
          case " ":
            applyBrake();
            break;
        }
      }

      function handleKeyUp(event) {
        if (!ntActive) {
          return;
        }
        const key = event.key.toLowerCase();
        if (key === "a") {
          finishTurn("left");
        } else if (key === "d") {
          finishTurn("right");
        }
      }

      document.addEventListener("keydown", handleKeyDown);
      document.addEventListener("keyup", handleKeyUp);

      const radarState = {
        maxDistance: 120,
        angleStep: 3,
        cells: new Array(61).fill(null),
      lastSweep: 0,
    };

    function degToRad(angle) {
      return Math.PI - (angle * Math.PI / 180);
    }

    function rebuildCells() {
      const slots = Math.floor(180 / radarState.angleStep) + 1;
      radarState.cells = new Array(slots).fill(null);
    }

    function recordRadar(angle, distance, valid) {
      if (!Number.isFinite(angle)) {
        return;
      }
      const idx = Math.max(0, Math.min(Math.round(angle / radarState.angleStep), radarState.cells.length - 1));
      radarState.cells[idx] = valid ? { angle, distance, at: Date.now() } : null;
    }

    function drawRadarBackground() {
      const radius = radarCanvas.width / 2;
      radarCtx.clearRect(0, 0, radarCanvas.width, radarCanvas.height);
      radarCtx.fillStyle = "#020b1b";
      radarCtx.fillRect(0, 0, radarCanvas.width, radarCanvas.height);
      radarCtx.strokeStyle = "#0b3923";
      radarCtx.lineWidth = 2;
      const rings = 4;
      for (let i = 1; i <= rings; i++) {
        const ringRadius = radius * (i / rings);
        radarCtx.beginPath();
        radarCtx.arc(radius, radius, ringRadius, Math.PI, 0);
        radarCtx.stroke();
      }
      for (let deg = 0; deg <= 180; deg += 30) {
        const rad = degToRad(deg);
        radarCtx.beginPath();
        radarCtx.moveTo(radius, radius);
        radarCtx.lineTo(radius + Math.cos(rad) * radius, radius - Math.sin(rad) * radius);
        radarCtx.stroke();
      }
    }

    function drawRadarSweep(angle, distance, valid) {
      const radius = radarCanvas.width / 2;
      const rad = degToRad(angle);
      const normalized = valid ? Math.max(0, Math.min(distance / radarState.maxDistance, 1)) : 0;
      const pingRadius = normalized * radius;

      // historical trail
      radarCtx.save();
      for (const entry of radarState.cells) {
        if (!entry) continue;
        const entryRad = degToRad(entry.angle);
        const ageMs = Date.now() - entry.at;
        const alpha = Math.max(0.15, 0.5 - ageMs / 4000);
        const entryRadius = Math.max(2, Math.min(entry.distance / radarState.maxDistance, 1) * radius);

        radarCtx.strokeStyle = `rgba(13, 255, 148, ${alpha.toFixed(3)})`;
        radarCtx.lineWidth = 2;
        radarCtx.beginPath();
        radarCtx.moveTo(radius, radius);
        radarCtx.lineTo(radius + Math.cos(entryRad) * entryRadius, radius - Math.sin(entryRad) * entryRadius);
        radarCtx.stroke();
      }
      radarCtx.restore();

      // sweep
      radarCtx.strokeStyle = "#1fffab";
      radarCtx.lineWidth = 3;
      radarCtx.beginPath();
      radarCtx.moveTo(radius, radius);
      radarCtx.lineTo(radius + Math.cos(rad) * radius, radius - Math.sin(rad) * radius);
      radarCtx.stroke();

      // current ping
      if (valid) {
        radarCtx.fillStyle = "#1fffab";
        radarCtx.beginPath();
        radarCtx.arc(radius + Math.cos(rad) * pingRadius, radius - Math.sin(rad) * pingRadius, 6, 0, 2 * Math.PI);
        radarCtx.fill();
      }
    }

    function handleRadar(data) {
      const payload = data.payload || data;
      if (data.sourceId && data.sourceId !== tankId) {
        return;
      }
      if (!payload || payload.sourceId && payload.sourceId !== tankId) {
        return;
      }

      if (Number.isFinite(payload.step_deg) && payload.step_deg > 0) {
        radarState.angleStep = Math.max(1, Math.min(15, Math.round(payload.step_deg)));
        rebuildCells();
      }
      if (Number.isFinite(payload.max_distance_cm) && payload.max_distance_cm > 0) {
        radarState.maxDistance = Math.min(200, payload.max_distance_cm);
      }

      const angle = Number(payload.angle) || 0;
      const distance = Number(payload.distance_cm);
      const valid = Boolean(payload.valid) && Number.isFinite(distance) && distance >= 0;

      recordRadar(angle, valid ? distance : 0, valid);
      drawRadarBackground();
      drawRadarSweep(angle, valid ? distance : 0, valid);

      if (valid) {
        radarSummary.textContent = `Angle ${angle.toFixed(0)}°, Distance ${distance.toFixed(1)} cm`;
      } else {
        radarSummary.textContent = `Angle ${angle.toFixed(0)}°, no echo`;
      }
    }

    drawRadarBackground();

    ws.onopen = () => {
      status.textContent = "Connected";
      write("Telemetry channel connected.");
    };
    ws.onclose = () => {
      status.textContent = "Disconnected";
      write("Telemetry channel closed.");
    };
    ws.onerror = (event) => {
      write("WebSocket error");
      console.error(event);
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry") {
          renderStatus(data);
        } else if (data.type === "radar") {
          handleRadar(data);
          return;
        }
        write(event.data);
      } catch (err) {
        write(event.data);
      }
    };

    async function sendCommand(command, options = {}) {
      const payload = {
        command,
        timestamp: new Date().toISOString(),
      };

      const left = options.leftSpeed;
      const right = options.rightSpeed;
      const sequence = options.sequence;

      if (typeof left === "number" && !Number.isNaN(left)) {
        payload.leftSpeed = clampSpeed(left);
      } else if (speedSlider) {
        payload.leftSpeed = clampSpeed(parseInt(speedSlider.value, 10));
      }
      if (typeof right === "number" && !Number.isNaN(right)) {
        payload.rightSpeed = clampSpeed(right);
      } else if (speedSlider) {
        payload.rightSpeed = clampSpeed(parseInt(speedSlider.value, 10));
      }
      if (sequence !== undefined) {
        payload.sequence = sequence;
      }

      try {
        const response = await fetch(`${apiBase}/command/${tankId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          let details = "";
          try {
            const err = await response.json();
            details = err.detail || "";
          } catch (parseErr) {
            details = response.statusText;
          }
          write(`Command error: ${details || response.statusText}`);
          return;
        }
        write(`Command sent: ${JSON.stringify(payload)}`);
      } catch (error) {
        write(`Command failed: ${error}`);
      }
    }

    document.querySelectorAll("button[data-command]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const command = btn.dataset.command;
        const options = command === "stop" ? { leftSpeed: 0, rightSpeed: 0 } : {};
        sendCommand(command, options);
      });
    });
  </script>
</body>
</html>
"""


@app.get("/controller/{tank_id}", response_class=HTMLResponse)
async def controller_ui(tank_id: str) -> HTMLResponse:
    html = CONTROLLER_TEMPLATE.replace("{{tank_id}}", tank_id)
    return HTMLResponse(content=html)

