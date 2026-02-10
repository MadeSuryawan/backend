# app/middleware/context.py
"""
Middleware for setting context variables during request lifecycle.

This middleware sets context variables (like cache_manager) in ContextVars
so that decorators and other code can access them without requiring
Request parameters in function signatures.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.context import cache_manager_ctx
from app.managers.cache_manager import CacheManager


class ContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to set context variables for request lifecycle.

    Sets cache_manager in ContextVars so decorators can access it
    without requiring Request parameter. Uses try/finally to ensure
    context is always reset after request processing.

    Examples
    --------
    >>> app.add_middleware(ContextMiddleware)
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """
        Set context and process request.

        Parameters
        ----------
        request : Request
            The incoming HTTP request.
        call_next : RequestResponseEndpoint
            The next middleware/endpoint in the chain.

        Returns
        -------
        Response
            The HTTP response from the downstream handler.
        """
        # Get cache manager from app state
        cache_manager: CacheManager | None = getattr(
            request.app.state,
            "cache_manager",
            None,
        )

        # Set context variable
        token = cache_manager_ctx.set(cache_manager)

        try:
            response = await call_next(request)
        finally:
            # Always reset context to prevent leakage between requests
            cache_manager_ctx.reset(token)

        return response
