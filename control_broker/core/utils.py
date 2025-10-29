"""Utility functions."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)
