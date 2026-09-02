"""
Centralised time source.

Always use this module instead of datetime.utcnow() or datetime.now().
This makes time injectable in tests and prevents timezone bugs.
"""

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


def utcnow_plus(seconds: int = 0, minutes: int = 0, hours: int = 0) -> datetime:
    """Return UTC time offset by given duration."""
    return utcnow() + timedelta(seconds=seconds, minutes=minutes, hours=hours)


def is_expired(dt: datetime) -> bool:
    """Return True if the given datetime is in the past."""
    return utcnow() > dt
