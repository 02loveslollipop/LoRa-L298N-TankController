"""Command validation models."""

from typing import Optional
from pydantic import BaseModel, ValidationError, validator


class CommandPayload(BaseModel):
    """Base command payload sent to tanks."""
    
    command: str
    leftSpeed: Optional[int] = None
    rightSpeed: Optional[int] = None
    sequence: Optional[int] = None
    timestamp: Optional[str] = None

    @validator("command")
    def validate_command(cls, value: str) -> str:
        """Validate command is in allowed set."""
        allowed = {"forward", "backward", "left", "right", "stop", "setspeed"}
        value_lower = value.lower()
        if value_lower not in allowed:
            raise ValueError(f"Unsupported command '{value}'.")
        return value_lower

    @validator("leftSpeed", "rightSpeed")
    def validate_speed(cls, value: Optional[int]) -> Optional[int]:
        """Validate speed is within valid range."""
        if value is None:
            return value
        if not 0 <= value <= 255:
            raise ValueError("Speed must be between 0 and 255.")
        return value


class StreamCommand(CommandPayload):
    """Command payload from Redis stream with tank ID."""
    
    tankId: str

    @validator("tankId")
    def validate_tank(cls, value: str) -> str:
        """Validate tank ID is not empty."""
        value = value.strip()
        if not value:
            raise ValueError("tankId is required")
        return value
