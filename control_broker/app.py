"""Tank Control Service - Main application."""

import asyncio
import json
from contextlib import suppress
from typing import List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from core import get_config, utcnow
from models import TankInfo
from services import ConnectionManager, RedisCommandListener


# Initialize FastAPI app
app = FastAPI(title="Tank Control Service", version="2.0.0")

# Load configuration
config = get_config()

# Initialize connection manager
manager = ConnectionManager()


# ========================================
# Lifecycle Events
# ========================================

@app.on_event("startup")
async def on_startup() -> None:
    """Initialize Redis connection and start command listener."""
    # For AWS ElastiCache/Valkey with TLS, disable certificate verification
    connection_kwargs = {"decode_responses": True}
    if config.redis_url.startswith("rediss://"):
        connection_kwargs["ssl_cert_reqs"] = None
        connection_kwargs["ssl_check_hostname"] = False
    
    app.state.redis = redis.from_url(config.redis_url, **connection_kwargs)
    
    # Start Redis command stream listener
    listener = RedisCommandListener(app.state.redis, config, manager)
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
    redis_client: Optional[redis.Redis] = getattr(app.state, "redis", None)
    
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
            if redis_client and isinstance(payload, dict):
                try:
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
                except Exception as stream_error:
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
