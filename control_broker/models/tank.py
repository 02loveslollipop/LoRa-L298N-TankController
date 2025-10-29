"""Tank connection information model."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from fastapi import WebSocket


@dataclass
class TankInfo:
    """Information about a connected tank."""
    
    tank_id: str
    connected_at: datetime
    last_seen: datetime
    last_payload: Optional[dict] = None
    commands_sent: int = 0
    websocket: Optional[WebSocket] = None
