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

    # Per-user timezone support
    from app.core.datetime_utils import user_local_time, is_in_delivery_window

    local_time = user_local_time(user.timezone)
    if is_in_delivery_window(user.timezone, user.delivery_time_local):
        send_digest(user)
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


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


# =============================================================================
# Per-user timezone utilities
# =============================================================================

# Common valid IANA timezones (subset for dropdown UX)
COMMON_TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "America/Vancouver",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Amsterdam",
    "Europe/Madrid",
    "Europe/Rome",
    "Europe/Stockholm",
    "Europe/Warsaw",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Hong_Kong",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Sydney",
    "Australia/Melbourne",
    "Pacific/Auckland",
]


def is_valid_timezone(tz_name: str) -> bool:
    """Check if a timezone name is valid IANA identifier.

    Args:
        tz_name: Timezone string (e.g., "America/New_York")

    Returns:
        True if valid IANA timezone
    """
    try:
        ZoneInfo(tz_name)
        return True
    except (KeyError, ValueError):
        return False


def user_local_time(timezone: str) -> datetime:
    """Get current time in a user's timezone.

    Args:
        timezone: IANA timezone string (e.g., "America/New_York")

    Returns:
        Aware datetime in user's local timezone
    """
    try:
        tz = ZoneInfo(timezone)
    except (KeyError, ValueError):
        # Fallback to UTC for invalid timezone
        tz = ZoneInfo("UTC")

    return datetime.now(tz)


def parse_delivery_time(delivery_time_local: str) -> time:
    """Parse a delivery time string (HH:MM) into a time object.

    Args:
        delivery_time_local: Time in "HH:MM" format (e.g., "08:00")

    Returns:
        time object, defaults to 08:00 if parsing fails
    """
    try:
        parts = delivery_time_local.split(":")
        return time(hour=int(parts[0]), minute=int(parts[1]))
    except (ValueError, IndexError):
        return time(hour=8, minute=0)


def is_in_delivery_window(
    timezone: str,
    delivery_time_local: str,
    window_minutes: int = 15,
) -> bool:
    """Check if current time is within user's delivery window.

    The delivery window is centered on the user's preferred delivery time,
    extending window_minutes in each direction.

    Args:
        timezone: User's IANA timezone (e.g., "America/New_York")
        delivery_time_local: User's preferred time in "HH:MM" format
        window_minutes: Window size in minutes (default 15 = ±15 min)

    Returns:
        True if current time is within delivery window
    """
    local_now = user_local_time(timezone)
    target_time = parse_delivery_time(delivery_time_local)

    # Create datetime for target time today in user's timezone
    target_dt = local_now.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )

    # Check if within window
    window = timedelta(minutes=window_minutes)
    return (target_dt - window) <= local_now <= (target_dt + window)


def has_delivery_window_passed(
    timezone: str,
    delivery_time_local: str,
) -> bool:
    """Check if user's delivery window has already passed today.

    Used for catch-up logic: if a user subscribes after their delivery time,
    we should send them the digest immediately.

    Args:
        timezone: User's IANA timezone
        delivery_time_local: User's preferred time in "HH:MM" format

    Returns:
        True if the delivery window has passed for today
    """
    local_now = user_local_time(timezone)
    target_time = parse_delivery_time(delivery_time_local)

    # Create datetime for target time today
    target_dt = local_now.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )

    # Window has passed if we're more than 15 minutes past the target time
    return local_now > (target_dt + timedelta(minutes=15))
