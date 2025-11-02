"""Tank Control Service - Main application."""

import asyncio
import json
from contextlib import suppress
from datetime import timedelta
from typing import List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis
from redis import exceptions as redis_exceptions
from redis.backoff import ExponentialBackoff
from redis.asyncio.retry import Retry

from core import get_config, utcnow
from models import TankInfo
from services import ConnectionManager, RadarBroker, RedisCommandListener


# Initialize FastAPI app
app = FastAPI(title="Tank Control Service", version="2.0.0")

# Load configuration
config = get_config()

# Initialize connection manager
manager = ConnectionManager()
radar_broker = RadarBroker()
redis_client_lock = asyncio.Lock()


def _build_connection_kwargs() -> dict:
    """Construct Redis connection keyword arguments."""
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
    if config.redis_url.startswith("rediss://"):
        kwargs["ssl_cert_reqs"] = None
        kwargs["ssl_check_hostname"] = False
    return kwargs


async def _create_redis_client() -> redis.Redis:
    """Create and validate a Redis client."""
    client = redis.from_url(config.redis_url, **_build_connection_kwargs())
    try:
        await client.ping()
    except Exception:
        await client.close()
        raise
    return client


async def reset_redis_client() -> redis.Redis:
    """Reset the shared Redis client instance."""
    async with redis_client_lock:
        existing = getattr(app.state, "redis", None)
        if existing is not None:
            app.state.redis = None
            await existing.close()
        new_client = await _create_redis_client()
        app.state.redis = new_client
        return new_client


async def get_redis_client() -> redis.Redis:
    """Get the current Redis client, lazily creating one if needed."""
    client = getattr(app.state, "redis", None)
    if client is None:
        return await reset_redis_client()
    return client


# ========================================
# Lifecycle Events
# ========================================

@app.on_event("startup")
async def on_startup() -> None:
    """Initialize Redis connection and start command listener."""
    await reset_redis_client()

    # Start Redis command stream listener
    listener = RedisCommandListener(get_redis_client, reset_redis_client, config, manager)
    app.state.command_listener = asyncio.create_task(listener.start())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Clean up Redis connection and stop listener."""
    listener = getattr(app.state, "command_listener", None)
    if listener:
        listener.cancel()
        with suppress(asyncio.CancelledError):
            await listener
    
    redis_client = getattr(app.state, "redis", None)
    if redis_client:
        await redis_client.close()
    app.state.redis = None


# ========================================
# Middleware
# ========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================
# REST Endpoints
# ========================================

@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": utcnow().isoformat(),
        "version": "2.0.0"
    }


@app.get("/tanks")
async def list_tanks() -> List[dict]:
    """List all registered tanks and their status."""
    return await manager.snapshot()


@app.get("/radars")
async def list_radars() -> List[dict]:
    """List all connected radar sources."""
    return await radar_broker.snapshot_sources()


# ========================================
# WebSocket Endpoints
# ========================================

@app.websocket("/ws/tank/{tank_id}")
async def tank_channel(websocket: WebSocket, tank_id: str) -> None:
    """WebSocket endpoint for tank connections."""
    try:
        await manager.register_tank(tank_id, websocket)
        print(f"[DEBUG] Tank {tank_id} registered successfully")

        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(), 
                    timeout=60.0
                )
                print(f"[DEBUG] Received from {tank_id}: {message[:100]}")
                
            except asyncio.TimeoutError:
                print(f"[DEBUG] Timeout waiting for message from {tank_id}, sending ping")
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": utcnow().isoformat()
                })
                continue
                
            except WebSocketDisconnect as disconnect:
                print(f"[DEBUG] Tank {tank_id} disconnect signal: code={disconnect.code}")
                raise
                
            except Exception as recv_error:
                print(f"[ERROR] Receive error for {tank_id}: {recv_error}")
                raise
                
            # Parse and store telemetry
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                payload = {"type": "telemetry", "raw": message}
                
            if isinstance(payload, dict):
                payload.setdefault("type", "telemetry")
                
            await manager.update_last_seen(
                tank_id,
                payload if isinstance(payload, dict) else None
            )

            # Store telemetry in Redis stream
            if isinstance(payload, dict):
                try:
                    redis_client = await get_redis_client()
                    await redis_client.xadd(
                        config.redis_status_stream,
                        {
                            "tankId": tank_id,
                            "payload": json.dumps(payload),
                            "receivedAt": utcnow().isoformat(),
                        },
                        maxlen=config.redis_status_maxlen,
                        approximate=True,
                    )
                except redis_exceptions.ConnectionError as stream_error:
                    print(f"[WARN] Redis connection lost while storing telemetry for {tank_id}: {stream_error}")
                    await reset_redis_client()
                except redis_exceptions.RedisError as stream_error:
                    print(f"[WARN] Failed to append telemetry to Redis: {stream_error}")
                    
    except WebSocketDisconnect:
        print(f"[DEBUG] Tank {tank_id} disconnected normally")
        await manager.unregister_tank(tank_id)
        
    except Exception as e:
        print(f"[ERROR] Tank {tank_id} error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        await manager.unregister_tank(tank_id)


@app.websocket("/ws/radar/source/{source_id}")
async def radar_source_channel(websocket: WebSocket, source_id: str) -> None:
    """WebSocket endpoint for radar hardware sources."""
    try:
        await radar_broker.register_source(source_id, websocket)
        print(f"[RADAR] Source {source_id} connected")

        while True:
            try:
                message = await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            except Exception as recv_error:
                print(f"[ERROR] Radar source {source_id} receive error: {recv_error}")
                raise

            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                payload = {"raw": message}

            if not isinstance(payload, dict):
                payload = {"raw": repr(payload)}

            payload.setdefault("type", "radar")
            payload["sourceId"] = source_id
            payload["receivedAt"] = utcnow().isoformat()

            serialized = json.dumps(payload)

            try:
                redis_client = await get_redis_client()
                await redis_client.xadd(
                    config.redis_radar_stream,
                    {
                        "sourceId": source_id,
                        "payload": serialized,
                        "receivedAt": payload["receivedAt"],
                    },
                    maxlen=config.redis_radar_maxlen,
                    approximate=True,
                )
            except redis_exceptions.ConnectionError as stream_error:
                print(f"[WARN] Radar Redis connection lost: {stream_error}")
                await reset_redis_client()
            except redis_exceptions.RedisError as stream_error:
                print(f"[WARN] Failed to append radar reading: {stream_error}")

            await radar_broker.broadcast(serialized)

    except WebSocketDisconnect:
        print(f"[RADAR] Source {source_id} disconnected")
    except Exception as exc:
        print(f"[ERROR] Radar source {source_id} error: {type(exc).__name__}: {exc}")
    finally:
        await radar_broker.unregister_source(source_id, websocket)


@app.websocket("/ws/radar/listener")
async def radar_listener_channel(websocket: WebSocket) -> None:
    """WebSocket endpoint for clients consuming radar data."""
    await radar_broker.register_listener(websocket)
    print("[RADAR] Listener connected")
    try:
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            except Exception as recv_error:
                print(f"[WARN] Radar listener receive error: {recv_error}")
                break
    except WebSocketDisconnect:
        print("[RADAR] Listener disconnected")
    finally:
        await radar_broker.unregister_listener(websocket)


# ========================================
# WSGI Compatibility
# ========================================

# For platforms expecting `application` variable
application = app
