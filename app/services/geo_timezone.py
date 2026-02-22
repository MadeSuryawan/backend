"""
IP-based timezone detection service.

Provides a fallback mechanism to detect user timezone via IP geolocation
when the frontend does not supply the X-Client-Timezone header.

This service is designed to be called only during user registration,
NOT on every request.
"""

from json import loads
from typing import Any

from httpx import AsyncClient, ConnectError, HTTPError, TimeoutException

from app.configs.settings import settings
from app.decorators.with_retry import with_retry
from app.monitoring import get_logger

logger = get_logger(__name__)


@with_retry(
    max_retries=3,
    base_delay=0.5,
    max_delay=2.0,
    exec_retry=(TimeoutException, ConnectError),
)
async def _fetch_timezone_from_api(client_ip: str) -> str:
    """
    Fetch timezone from API with retry logic.

    Raies:
        HTTPError: If the API returns a non-200 status code.
        TimeoutException: If the request times out.
        ConnectError: If the connection fails.
    """
    url = (
        f"https://api.ipgeolocation.io/v3/timezone"
        f"?apiKey={settings.IP_GEOLOCATION_API_KEY}&ip={client_ip}"
    )

    async with AsyncClient(timeout=3.0) as client:
        response = await client.get(url)
        if response.status_code == 200:
            data: dict[str, Any] = loads(response.text)
            tz_data: dict[str, Any] = data.get("time_zone", {})
            tz_name = tz_data.get("name", "UTC")
            return tz_name

        # Raise HTTPError for non-200 status codes to trigger potential handling/logging
        # deeper in the stack or just to be caught by the main wrapper.
        # However, for 4xx/5xx we might NOT want to retry depending on the code.
        # For now, we'll treat them as failures that fall back to UTC immediately
        # unless we add them to exec_retry.
        response.raise_for_status()
        return "UTC"  # Should be unreachable due to raise_for_status


async def detect_timezone_by_ip(client_ip: str) -> str:
    """
    Detect timezone from IP address via geolocation API.

    Uses the ipgeolocation.io API as a fallback when the frontend
    does not supply timezone data. Returns 'UTC' on any failure.

    Args:
        client_ip: Client's IP address string.

    Returns:
        IANA timezone string (e.g., 'America/New_York') or 'UTC' on failure.

    Example:
        >>> tz = await detect_timezone_by_ip("8.8.8.8")
        >>> tz
        'America/Chicago'

    """
    if not settings.IP_GEOLOCATION_API_KEY:
        logger.debug("IP_GEOLOCATION_API_KEY not configured, defaulting to UTC")
        return "UTC"

    try:
        return await _fetch_timezone_from_api(client_ip)
    except (HTTPError, TimeoutException, ConnectError, ValueError) as e:
        logger.warning(f"IP geolocation failed for IP: {client_ip}: {e}, defaulting to UTC")

    return "UTC"
