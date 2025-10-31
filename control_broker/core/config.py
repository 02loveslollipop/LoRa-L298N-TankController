"""Configuration management."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration."""
    
    redis_url: str
    redis_command_stream: str
    redis_command_stream_start: str
    redis_status_stream: str
    redis_status_maxlen: int
    redis_radar_stream: str
    redis_radar_maxlen: int


def get_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        redis_command_stream=os.getenv("REDIS_COMMAND_STREAM", "tank_commands"),
        redis_command_stream_start=os.getenv("REDIS_COMMAND_STREAM_START", "0-0"),
        redis_status_stream=os.getenv("REDIS_STATUS_STREAM", "tank_status"),
        redis_status_maxlen=int(os.getenv("REDIS_STATUS_MAXLEN", "500")),
        redis_radar_stream=os.getenv("REDIS_RADAR_STREAM", "tank_radar"),
        redis_radar_maxlen=int(os.getenv("REDIS_RADAR_MAXLEN", "1000")),
    )
