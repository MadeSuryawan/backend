from datetime import datetime
from time import perf_counter
from typing import Any

from fastapi import Request

from app.models.blog import BlogDB
from app.models.review import ReviewDB
from app.models.user import UserDB
from app.utils.timezone import format_api_response


def today_str() -> str:
    """Return today's date as a string."""
    return datetime.now(datetime.now().astimezone().tzinfo).strftime(
        "%Y-%m-%d %H:%M:%S",
    )


def host(request: Request) -> str:
    """Return the host IP address."""
    return request.client.host if request.client else "unknown"


def time_taken(start_time: float) -> str:
    minutes, seconds = divmod(perf_counter() - start_time, 60)
    formatted_time = f"{int(minutes)}m {seconds:.2f}s"

    return formatted_time


def response_datetime(
    db: UserDB | BlogDB | ReviewDB,
    user_timezone: str = "UTC",
) -> dict[str, Any]:
    """
    Format datetime for response with user's local timezone.

    Args:
        db: Database model with timestamps.
        user_timezone: IANA timezone string (e.g., 'America/New_York').
            Defaults to 'UTC'.

    Returns:
        Dictionary with formatted datetime objects containing
        utc, local, human-friendly, and timezone information.

    Example:
        >>> db_dict = response_datetime(user_db, "America/New_York")
        >>> db_dict["created_at"]
        {
            'utc': '2026-02-13T15:00:00+00:00',
            'local': 'Friday, February 13, 2026 10:00 AM',
            'human': '5 hours ago',
            'timezone': 'America/New_York'
        }

    """
    db_dict = db.model_dump()

    # Convert created_at to multi-format response
    db_dict["created_at"] = format_api_response(db.created_at, user_timezone)

    # Convert updated_at if exists
    if db.updated_at:
        db_dict["updated_at"] = format_api_response(db.updated_at, user_timezone)
    else:
        db_dict["updated_at"] = None

    return db_dict
