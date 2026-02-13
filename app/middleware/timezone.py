"""
Timezone detection middleware for FastAPI.

Detects the user's timezone from the X-Client-Timezone header.
Falls back to UTC if the header is not present.

The detected timezone is stored in request.state.user_timezone
for use in response formatting.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class TimezoneMiddleware(BaseHTTPMiddleware):
    """
    Middleware for detecting user's timezone from request headers.

    Sets request.state.user_timezone from X-Client-Timezone header,
    defaulting to UTC if not provided.

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
        Extract timezone from header and store in request state.

        Args:
            request: Current HTTP request.
            call_next: Next middleware/endpoint in chain.

        Returns:
            HTTP response from downstream handlers.

        """
        request.state.user_timezone = request.headers.get(
            "X-Client-Timezone",
            "UTC",
        )
        return await call_next(request)
