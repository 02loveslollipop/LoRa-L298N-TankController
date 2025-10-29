import asyncio
import json
import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from redis import exceptions as redis_exceptions
from redis.backoff import ExponentialBackoff
from redis.asyncio.retry import Retry
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_COMMAND_STREAM = os.getenv("REDIS_COMMAND_STREAM", "tank_commands")
REDIS_STATUS_STREAM = os.getenv("REDIS_STATUS_STREAM", "tank_status")
RETENTION_MINUTES = int(os.getenv("STREAM_RETENTION_MINUTES", "30"))
CLEAN_INTERVAL_SECONDS = int(os.getenv("STREAM_CLEAN_INTERVAL_SECONDS", str(24 * 3600)))

app = FastAPI(title="Stream Cleaner Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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


async def trim_stream(redis_client: redis.Redis, stream: str, threshold_ms: int) -> int:
    min_id = f"{threshold_ms}-0"
    try:
        trimmed = await redis_client.xtrim(stream, minid=min_id, approximate=True)
        return trimmed or 0
    except redis_exceptions.ConnectionError as exc:
        print(f"[CLEANER] Redis connection lost while trimming '{stream}': {exc}")
        await reset_redis_client()
        return 0
    except redis_exceptions.RedisError as exc:
        print(f"[CLEANER] Failed trimming stream '{stream}': {exc}")
        return 0


async def run_cleanup(redis_client: redis.Redis) -> dict:
    threshold = utcnow() - timedelta(minutes=RETENTION_MINUTES)
    threshold_ms = int(threshold.timestamp() * 1000)
    streams = [REDIS_COMMAND_STREAM, REDIS_STATUS_STREAM]
    report = {}

    for stream in streams:
        trimmed = await trim_stream(redis_client, stream, threshold_ms)
        report[stream] = trimmed

    print(f"[CLEANER] Cleanup completed @ {utcnow().isoformat()} :: {json.dumps(report)}")
    return report


async def cleaner_loop(redis_client: redis.Redis) -> None:
    while True:
        client = await get_redis_client()
        await run_cleanup(client)
        await asyncio.sleep(CLEAN_INTERVAL_SECONDS)


@app.on_event("startup")
async def on_startup() -> None:
    client = await reset_redis_client()
    app.state.cleaner_task = asyncio.create_task(cleaner_loop(client))


@app.on_event("shutdown")
async def on_shutdown() -> None:
    task = getattr(app.state, "cleaner_task", None)
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    redis_client = getattr(app.state, "redis", None)
    if redis_client:
        await redis_client.close()
    app.state.redis = None


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "timestamp": utcnow().isoformat(),
        "retentionMinutes": RETENTION_MINUTES,
        "intervalSeconds": CLEAN_INTERVAL_SECONDS,
    }


@app.post("/cleanup")
async def cleanup() -> dict:
    client = await get_redis_client()
    report = await run_cleanup(client)
    return {"status": "ok", "report": report}
