"""
Timezone detection middleware for FastAPI.

This middleware detects the user's timezone from:
1. X-Client-Timezone header (from frontend)
2. IP geolocation (fallback)
3. Default to UTC (final fallback)

The detected timezone is stored in request.state.user_timezone
for use in response formatting.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.utils.timezone import DEFAULT_USER_TIMEZONE


class TimezoneMiddleware(BaseHTTPMiddleware):
    """
    Middleware for detecting and storing user's timezone.

    This middleware detects the user's preferred timezone using multiple
    methods and stores it in request.state.user_timezone for use by
    response formatters and other middleware.

    Detection priority:
    1. X-Client-Timezone header from frontend (highest priority)
    2. IP geolocation (fallback)
    3. Default to UTC (final fallback)

    Examples:
        >>> # In a route
        >>> @app.get("/example")
        >>> async def example(request: Request):
        ...     tz = request.state.user_timezone
        ...     return {"timezone": tz}

    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Detect timezone and store in request state.

        Args:
            request: Current HTTP request.
            call_next: Next middleware/endpoint in chain.

        Returns:
            HTTP response from downstream handlers.

        """
        # Detect timezone using priority order
        user_timezone = self._detect_timezone(request)
        request.state.user_timezone = user_timezone

        # Continue with request processing
        response = await call_next(request)
        return response

    def _detect_timezone(self, request: Request) -> str:
        """
        Detect timezone from request using multiple methods.

        Priority order:
        1. X-Client-Timezone header from frontend
        2. IP geolocation (fallback)
        3. Default UTC (final fallback)

        Args:
            request: Current HTTP request.

        Returns:
            Detected timezone string (e.g., 'America/New_York').

        """
        # Priority 1: Check X-Client-Timezone header from frontend
        if client_tz := request.headers.get("X-Client-Timezone"):
            return client_tz

        # Priority 2: Try IP geolocation
        client_ip = request.client.host if request.client else None
        if client_ip and (detected_tz := self._call_ip_geolocation_api(client_ip)):
            return detected_tz

        # Priority 3: Default to UTC
        return DEFAULT_USER_TIMEZONE

    def _call_ip_geolocation_api(self, client_ip: str) -> str | None:
        """
        Call IP geolocation API to detect timezone.

        This is a simplified implementation. In production, you would use
        a geolocation service like MaxMind GeoIP2 or ipapi.co.

        Args:
            client_ip: Client's IP address.

        Returns:
            Timezone string (e.g., 'America/New_York') or None if detection fails.

        Example:
            >>> detect_timezone_from_ip("8.8.8.8")  # Google DNS (US)
            'America/Los_Angeles'
            >>> detect_timezone_from_ip("1.1.1.1")  # Cloudflare (AU)
            'Australia/Sydney'

        """
        # TODO: Implement actual IP geolocation service
        # For now, return None to use default
        # Options for implementation:
        # 1. MaxMind GeoIP2 (requires database file)
        # 2. ipapi.co (free tier available, HTTP API)
        # 3. ipgeolocation.io (free tier available)

        # Placeholder implementation - returns None to use default
        return None
