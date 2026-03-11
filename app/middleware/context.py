# app/middleware/context.py
"""
Middleware for setting context variables during request lifecycle.

This middleware sets context variables (like cache_manager) in ContextVars
so that decorators and other code can access them without requiring
Request parameters in function signatures.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.context import cache_manager_ctx
from app.managers.cache_manager import CacheManager


class ContextMiddleware:
    """
    Middleware to set context variables for request lifecycle.

    Sets cache_manager in ContextVars so decorators can access it
    without requiring Request parameter. Uses try/finally to ensure
    context is always reset after request processing.

    Examples
    --------
    >>> app.add_middleware(ContextMiddleware)
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
        Set context and process request.

        Parameters
        ----------
        scope : Scope
            The incoming ASGI connection scope.
        receive : Receive
            ASGI receive callable.
        send : Send
            ASGI send callable.
        """
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Get cache manager from app state
        cache_manager: CacheManager | None = getattr(
            scope["app"].state,
            "cache_manager",
            None,
        )

        # Set context variable
        token = cache_manager_ctx.set(cache_manager)

        try:
            await self._app(scope, receive, send)
        finally:
            # Always reset context to prevent leakage between requests
            cache_manager_ctx.reset(token)
