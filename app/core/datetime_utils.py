"""Centralized datetime utilities for consistent timezone handling.

This module provides timezone-aware datetime functions to replace deprecated
`datetime.utcnow()` calls. All functions return naive datetimes for database
compatibility (SQLAlchemy models use naive UTC).

Usage:
    from app.core.datetime_utils import utc_now, is_expired, get_cutoff

    # Current time
    now = utc_now()

    # Check expiry
    if is_expired(token.expires_at):
        raise TokenExpired()

    # Get cutoff for queries
    cutoff = get_cutoff(hours=24)
    items = query.filter(Item.created_at > cutoff)
"""

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """Get current UTC time as naive datetime.

    Returns naive datetime for database compatibility.
    Replaces deprecated datetime.utcnow().
    """
    return datetime.now(UTC).replace(tzinfo=None)


def is_expired(expires_at: datetime) -> bool:
    """Check if a timestamp has expired.

    Args:
        expires_at: Expiry timestamp (naive UTC)

    Returns:
        True if current time is past expires_at
    """
    return utc_now() > expires_at


def get_cutoff(hours: int = 0, days: int = 0) -> datetime:
    """Get cutoff datetime for filtering queries.

    Args:
        hours: Hours to subtract from now
        days: Days to subtract from now

    Returns:
        Naive UTC datetime representing the cutoff point
    """
    delta = timedelta(hours=hours, days=days)
    return utc_now() - delta


def get_expiry(minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    """Get future expiry datetime.

    Args:
        minutes: Minutes to add to now
        hours: Hours to add to now
        days: Days to add to now

    Returns:
        Naive UTC datetime representing the expiry point
    """
    delta = timedelta(minutes=minutes, hours=hours, days=days)
    return utc_now() + delta


def to_naive_utc(dt: datetime) -> datetime:
    """Convert a datetime to naive UTC.

    Args:
        dt: Datetime to convert (can be aware or naive)

    Returns:
        Naive UTC datetime for database compatibility
    """
    if dt.tzinfo is None:
        # Already naive, assume it's UTC
        return dt
    # Convert to UTC and strip timezone
    return dt.astimezone(UTC).replace(tzinfo=None)
