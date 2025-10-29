"""WebSocket connection manager for tanks."""

import asyncio
import json
from typing import Dict, List, Optional
from fastapi import WebSocket

from models import TankInfo
from core import utcnow


class ConnectionManager:
    """Manages WebSocket connections to tanks."""
    
    def __init__(self) -> None:
        self._tanks: Dict[str, TankInfo] = {}
        self._lock = asyncio.Lock()

    async def register_tank(self, tank_id: str, websocket: WebSocket) -> TankInfo:
        """Register a new tank connection."""
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
            info = TankInfo(
                tank_id=tank_id,
                connected_at=utcnow(),
                last_seen=utcnow(),
                last_payload=previous.last_payload if previous else None,
                commands_sent=previous.commands_sent if previous else 0,
                websocket=websocket,
            )
            self._tanks[tank_id] = info
            return info

    async def unregister_tank(self, tank_id: str) -> None:
        """Unregister a tank connection."""
        async with self._lock:
            info = self._tanks.get(tank_id)
            if not info:
                return
            info.websocket = None
            info.last_seen = utcnow()

    async def forward_to_tank(self, tank_id: str, payload: dict) -> None:
        """Forward a command to a specific tank."""
        async with self._lock:
            info = self._tanks.get(tank_id)
            if not info or not info.websocket:
                raise LookupError("Tank is not connected.")
            info.commands_sent += 1
            websocket = info.websocket
        await websocket.send_text(json.dumps(payload))

    def snapshot(self) -> List[dict]:
        """Get a snapshot of all tank statuses."""
        now = utcnow()
        result: List[dict] = []
        for info in self._tanks.values():
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
