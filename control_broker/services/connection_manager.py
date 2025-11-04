"""WebSocket connection manager for tanks."""

import asyncio
import json
from contextlib import suppress
from datetime import timedelta
from typing import Dict, List, Optional, Tuple
from fastapi import WebSocket

from models import TankInfo
from core import utcnow


class ConnectionManager:
    """Manages WebSocket connections to tanks."""
    
    def __init__(
        self,
        *,
        stale_timeout_seconds: int = 600,
        prune_interval_seconds: int = 30,
    ) -> None:
        self._tanks: Dict[str, TankInfo] = {}
        self._lock = asyncio.Lock()
        self._stale_timeout = timedelta(seconds=max(1, stale_timeout_seconds))
        self._prune_interval = timedelta(seconds=max(5, prune_interval_seconds))
        self._maintenance_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start background maintenance tasks."""
        if self._maintenance_task and not self._maintenance_task.done():
            return
        self._maintenance_task = asyncio.create_task(self._run_auto_prune())

    async def stop(self) -> None:
        """Stop maintenance tasks and wait for completion."""
        task = self._maintenance_task
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._maintenance_task = None

    async def _run_auto_prune(self) -> None:
        """Periodically prune stale tank connections."""
        try:
            while True:
                await asyncio.sleep(self._prune_interval.total_seconds())
                await self._prune_stale(reason="auto-prune")
        except asyncio.CancelledError:
            pass

    async def _prune_stale(self, *, reason: str = "stale") -> None:
        """Remove tanks that have been inactive for longer than the timeout."""
        now = utcnow()
        to_close: List[Tuple[str, WebSocket]] = []
        async with self._lock:
            for tank_id, info in list(self._tanks.items()):
                if (now - info.last_seen) > self._stale_timeout:
                    websocket = info.websocket
                    if websocket is not None:
                        to_close.append((tank_id, websocket))
                    self._tanks.pop(tank_id, None)
        for tank_id, websocket in to_close:
            with suppress(Exception):
                await websocket.close(code=1011)
            print(f"[MANAGER] Pruned tank '{tank_id}' due to {reason}")

    async def register_tank(self, tank_id: str, websocket: WebSocket) -> TankInfo:
        """Register a new tank connection."""
        await self._prune_stale()
        await websocket.accept()
        await websocket.send_text(
            json.dumps(
                {"type": "hello", "tankId": tank_id, "acceptedAt": utcnow().isoformat()}
            )
        )
        async with self._lock:
            previous = self._tanks.get(tank_id)
            if previous and previous.websocket:
                await previous.websocket.close(code=1011)
            now = utcnow()
            info = TankInfo(
                tank_id=tank_id,
                connected_at=now,
                last_seen=now,
                last_payload=previous.last_payload if previous else None,
                commands_sent=previous.commands_sent if previous else 0,
                websocket=websocket,
            )
            self._tanks[tank_id] = info
            return info

    async def unregister_tank(self, tank_id: str) -> None:
        """Unregister a tank connection."""
        await self._prune_stale()
        async with self._lock:
            info = self._tanks.get(tank_id)
            if not info:
                return
            info.websocket = None
            info.last_seen = utcnow()

    async def forward_to_tank(self, tank_id: str, payload: dict) -> None:
        """Forward a command to a specific tank."""
        await self._prune_stale()
        async with self._lock:
            info = self._tanks.get(tank_id)
            if not info or not info.websocket:
                raise LookupError("Tank is not connected.")
            info.commands_sent += 1
            websocket = info.websocket
        await websocket.send_text(json.dumps(payload))

    async def snapshot(self) -> List[dict]:
        """Get a snapshot of all tank statuses, pruning stale entries."""
        await self._prune_stale()
        now = utcnow()
        async with self._lock:
            infos = list(self._tanks.values())
        result: List[dict] = []
        for info in infos:
            result.append(
                {
                    "tankId": info.tank_id,
                    "connected": info.websocket is not None,
                    "connectedAt": info.connected_at.isoformat(),
                    "lastSeen": info.last_seen.isoformat(),
                    "commandsSent": info.commands_sent,
                    "lastPayload": info.last_payload,
                    "stale": (now - info.last_seen).total_seconds(),
                }
            )
        return result

    async def update_last_seen(self, tank_id: str, payload: Optional[dict]) -> None:
        """Update the last seen timestamp for a tank."""
        async with self._lock:
            info = self._tanks.get(tank_id)
            if not info:
                return
            info.last_seen = utcnow()
            if payload is not None:
                info.last_payload = payload

    async def force_reset(self, tank_id: str) -> bool:
        """Forcefully terminate and remove a tank connection."""
        async with self._lock:
            info = self._tanks.pop(tank_id, None)
        if not info:
            return False
        websocket = info.websocket
        if websocket:
            with suppress(Exception):
                await websocket.close(code=1012)
        print(f"[MANAGER] Forced reset for tank '{tank_id}'")
        return True

    async def close_all(self) -> None:
        """Close all tracked tank connections."""
        async with self._lock:
            entries = list(self._tanks.items())
            self._tanks.clear()
        for tank_id, info in entries:
            websocket = info.websocket
            if websocket:
                with suppress(Exception):
                    await websocket.close(code=1001)
            print(f"[MANAGER] Closed connection for tank '{tank_id}' during shutdown")
