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
from services import ConnectionManager, RedisCommandListener


# Initialize FastAPI app
app = FastAPI(title="Tank Control Service", version="2.0.0")

# Load configuration
config = get_config()

# Initialize connection manager
manager = ConnectionManager()
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
    return manager.snapshot()


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


# ========================================
# WSGI Compatibility
# ========================================

# For platforms expecting `application` variable
application = app
