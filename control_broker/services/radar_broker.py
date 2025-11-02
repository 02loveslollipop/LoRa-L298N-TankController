"""Radar WebSocket broker for distributing readings."""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import WebSocket
from starlette.websockets import WebSocketState


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RadarBroker:
    """Manages radar data sources and listeners."""

    def __init__(self) -> None:
        self._listeners: Set[WebSocket] = set()
        self._listeners_lock = asyncio.Lock()
        self._sources: Dict[str, WebSocket] = {}
        self._sources_meta: Dict[str, datetime] = {}
        self._sources_lock = asyncio.Lock()

    async def register_listener(self, websocket: WebSocket) -> None:
        """Accept a listener connection and keep track of it."""
        await websocket.accept()
        async with self._listeners_lock:
            self._listeners.add(websocket)

    async def unregister_listener(self, websocket: WebSocket) -> None:
        """Remove a listener connection."""
        async with self._listeners_lock:
            self._listeners.discard(websocket)

    async def register_source(self, source_id: str, websocket: WebSocket) -> None:
        """Accept a radar source connection, replacing any previous one."""
        await websocket.accept()
        async with self._sources_lock:
            previous = self._sources.get(source_id)
            if previous and previous.application_state == WebSocketState.CONNECTED:
                await previous.close(code=1011)
            self._sources[source_id] = websocket
            self._sources_meta[source_id] = _utcnow()

    async def unregister_source(self, source_id: str, websocket: WebSocket) -> None:
        """Remove the radar source connection if it matches."""
        async with self._sources_lock:
            existing = self._sources.get(source_id)
            if existing is websocket:
                self._sources.pop(source_id, None)
                self._sources_meta.pop(source_id, None)

    async def snapshot_sources(self) -> List[dict]:
        """Return metadata about connected radar sources."""
        async with self._sources_lock:
            return [
                {
                    "sourceId": source_id,
                    "connected": websocket.application_state == WebSocketState.CONNECTED,
                    "connectedAt": self._sources_meta.get(source_id, _utcnow()).isoformat(),
                }
                for source_id, websocket in self._sources.items()
            ]

    async def broadcast(self, payload: str) -> None:
        """Broadcast a radar payload to all listeners."""
        async with self._listeners_lock:
            listeners = list(self._listeners)

        stale: Set[WebSocket] = set()
        for websocket in listeners:
            try:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.send_text(payload)
                else:
                    stale.add(websocket)
            except Exception:
                stale.add(websocket)

        if stale:
            async with self._listeners_lock:
                for websocket in stale:
                    self._listeners.discard(websocket)
