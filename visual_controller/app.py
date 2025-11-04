import asyncio
import json
import os
from collections import defaultdict
from contextlib import suppress
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from pathlib import Path

import httpx
import redis.asyncio as redis
from redis import exceptions as redis_exceptions
from redis.backoff import ExponentialBackoff
from redis.asyncio.retry import Retry
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
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

BASE_DIR = Path(__file__).resolve().parent
SPA_STATIC_DIR = BASE_DIR / "static"
SPA_INDEX_FILE = SPA_STATIC_DIR / "index.html"

assets_dir = SPA_STATIC_DIR / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


def _serve_spa() -> FileResponse:
    if SPA_INDEX_FILE.exists():
        return FileResponse(SPA_INDEX_FILE)
    raise HTTPException(status_code=503, detail="UI bundle not found. Run the frontend build script.")


@app.get("/", response_class=FileResponse)
async def serve_root() -> FileResponse:
    return _serve_spa()


@app.get("/legacy", response_class=FileResponse)
async def serve_legacy() -> FileResponse:
    return _serve_spa()


@app.get("/nt", response_class=FileResponse)
async def serve_nt() -> FileResponse:
    return _serve_spa()


@app.get("/status", response_class=FileResponse)
async def serve_status() -> FileResponse:
    return _serve_spa()


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




