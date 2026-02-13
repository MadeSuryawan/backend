"""
Timezone utility functions for handling datetime conversions.

This module provides utilities for:
- Formatting datetimes for API responses and logs
- Human-friendly relative time formatting
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def format_logs(dt: datetime, timezone: str) -> str:
    """
    Format datetime for server logs in the specified timezone.

    Args:
        dt: Datetime object (timezone-aware).
        timezone: IANA timezone string (e.g., 'Asia/Makassar').

    Returns:
        Formatted string in the specified timezone.

    Example:
        >>> dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        >>> format_logs(dt, "Asia/Makassar")
        '13/02/26 23:00:00 WITA'

    """
    return dt.astimezone(ZoneInfo(timezone)).strftime("%d/%m/%y %H:%M:%S %Z")


def format_api_response(dt: datetime, user_timezone: str) -> dict[str, str]:
    """
    Format datetime for API response with multiple representations.

    Args:
        dt: Datetime object (timezone-aware, stored as UTC).
        user_timezone: User's preferred IANA timezone (e.g., 'America/New_York').

    Returns:
        Dictionary with UTC (ISO 8601 with offset), local (human-readable),
        human-friendly relative time, and timezone info.

    Example:
        >>> dt = datetime(2026, 2, 13, 15, 0, 0, tzinfo=UTC)
        >>> format_api_response(dt, "America/New_York")
        {
            'utc': '2026-02-13T10:00:00-0500',
            'local': 'Friday, February 13, 2026 10:00:00',
            'human': '5 hours ago',
            'timezone': 'America/New_York'
        }

    """
    user_tz = ZoneInfo(user_timezone)
    local_dt = dt.astimezone(user_tz)

    return {
        "utc": local_dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "local": local_dt.strftime("%A, %B %d, %Y %H:%M:%S"),
        "human": humanize_time(dt),
        "timezone": user_tz.key,
    }


def humanize_time(dt: datetime) -> str:
    """
    Convert datetime to human-friendly relative time.

    Args:
        dt: Datetime object (timezone-aware).

    Returns:
        Human-friendly string like "Just now", "5 minutes ago", "Yesterday".

    Examples:
        >>> humanize_time(datetime.now(UTC))
        'Just now'
        >>> humanize_time(datetime.now(UTC) - timedelta(minutes=5))
        '5 minutes ago'
        >>> humanize_time(datetime.now(UTC) - timedelta(days=1))
        'Yesterday at 03:00 PM'

    """
    now = datetime.now(UTC)
    diff = now - dt

    if diff < timedelta(minutes=1):
        return "Just now"
    if diff < timedelta(hours=1):
        minutes = int(diff.seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    if diff < timedelta(days=1):
        hours = int(diff.seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    if diff < timedelta(days=2):
        return f"Yesterday at {dt.strftime('%I:%M %p')}"
    if diff < timedelta(days=7):
        return f"{diff.days} days ago"
    return dt.strftime("%b %d, %Y")
