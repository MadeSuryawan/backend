from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from app.managers.metrics import MetricsManager, RequestTimer

# Type variables for generic decorator
P = ParamSpec("P")
R = TypeVar("R")


def timed(
    endpoint: str | None = None,
    metrics: MetricsManager | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """
    Time async functions with automatic metrics recording.

    Args:
        endpoint: API endpoint path (defaults to function name).
        metrics: Optional metrics manager (defaults to global instance).

    Returns:
        Decorated function with timing instrumentation.

    Example:
        @timed("/api/items")
        async def get_items() -> list[Item]:
            ...
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        ep = endpoint or func.__name__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            async with RequestTimer(ep, metrics):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
