# app/context/__init__.py
"""
Context variables for cross-cutting concerns.

This module provides context variables that can be accessed throughout
a request lifecycle without explicitly passing them through function signatures.
"""

from contextvars import ContextVar

from app.managers.cache_manager import CacheManager

#: Context variable for cache manager access.
#: Set by ContextMiddleware during request processing.
#: Decorators can access this to get the cache manager without requiring
#: a Request parameter in the function signature.
cache_manager_ctx: ContextVar[CacheManager | None] = ContextVar(
    "cache_manager",
    default=None,
)

__all__ = ["cache_manager_ctx"]
