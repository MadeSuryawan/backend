"""
Timezone detection middleware for FastAPI.

Detects the user's timezone from the X-Client-Timezone header.
Falls back to UTC if the header is not present.

The detected timezone is stored in request.state.user_timezone
for use in response formatting.
"""

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send


class TimezoneMiddleware:
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

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Extract timezone from header and store in request state.

        Args:
            scope: Current ASGI connection scope.
            receive: ASGI receive callable.
            send: ASGI send callable.

        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        headers = Headers(scope=scope)
        state["user_timezone"] = headers.get(
            "X-Client-Timezone",
            "UTC",
        )
        await self._app(scope, receive, send)
