"""
Timezone utility functions for handling datetime conversions.

This module provides utilities for:
- Converting datetimes between timezones
- Formatting datetimes for API responses and logs
- Human-friendly relative time formatting
- IP-based timezone detection
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Request

# Constants
DEFAULT_USER_TIMEZONE = "UTC"


def get_user_timezone(request: Request) -> str:
    """
    Get timezone from request state or return default.

    Args:
        request: Current HTTP request with state containing user_timezone.

    Returns:
        User's timezone string (e.g., 'America/New_York') or 'UTC' as default.

    Example:
        >>> tz = get_user_timezone(request)
        >>> tz
        'America/New_York'

    """
    return getattr(request.state, "user_timezone", DEFAULT_USER_TIMEZONE)


def format_logs(dt: datetime, timezone: str) -> str:
    """
    Format datetime for server logs.

    Args:
        dt: Datetime object (timezone-aware).
        timezone: Timezone string (e.g., 'Asia/Singapore').

    Returns:
        Formatted string in the specified timezone.

    Example:
        >>> dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        >>> format_logs(dt)
        '2026-02-13 23:00:00 WIB'

    """
    _tz = ZoneInfo(timezone)
    return dt.astimezone(_tz).strftime("%d/%m/%y %H:%M:%S %Z")


def format_api_response(dt: datetime, user_timezone: str) -> dict[str, str]:
    """
    Format datetime for API response with multiple representations.

    Args:
        dt: Datetime object (timezone-aware, stored as UTC).
        user_timezone: User's preferred timezone (e.g., 'America/New_York').

    Returns:
        Dictionary with UTC, local, human-friendly, and timezone info.

    Example:
        >>> dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        >>> format_api_response(dt, "America/New_York")
        {
            'utc': '2026-02-13T15:00:00Z',
            'local': '2026-02-13 10:00:00 EST',
            'human': '5 hours ago',
            'timezone': 'America/New_York'
        }

    """
    user_tz = ZoneInfo(user_timezone)
    local_dt = dt.astimezone(user_tz)

    return {
        "utc": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "local": local_dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "human": humanize_time(dt),
        "timezone": user_timezone,
    }


def humanize_time(dt: datetime) -> str:
    """
    Convert datetime to human-friendly relative time.

    Args:
        dt: Datetime object (timezone-aware).

    Returns:
        Human-friendly string like "Just now", "5 minutes ago", "Yesterday".

    Examples:
        >>> humanize_time(datetime.now(UTC))  # Just now
        'Just now'
        >>> humanize_time(datetime.now(UTC) - timedelta(minutes=5))  # 5 min ago
        '5 minutes ago'
        >>> humanize_time(datetime.now(UTC) - timedelta(hours=2))  # 2 hours ago
        '2 hours ago'
        >>> humanize_time(datetime.now(UTC) - timedelta(days=1))  # Yesterday
        'Yesterday'
        >>> humanize_time(datetime.now(UTC) - timedelta(days=5))  # Days ago
        '5 days ago'
        >>> humanize_time(datetime(2026, 2, 1, 10, 0, 0, tzinfo=UTC))  # Older
        'Feb 01, 2026'

    """
    now = datetime.now(UTC)
    diff = now - dt

    if diff < timedelta(minutes=1):
        return "Just now"
    elif diff < timedelta(hours=1):
        minutes = int(diff.seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif diff < timedelta(days=1):
        hours = int(diff.seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff < timedelta(days=2):
        return f"Yesterday at {dt.strftime('%I:%M %p')}"
    elif diff < timedelta(days=7):
        return f"{diff.days} days ago"
    else:
        return dt.strftime("%b %d, %Y")
