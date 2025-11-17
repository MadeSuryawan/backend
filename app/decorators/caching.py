"""FastAPI decorators for caching with rate limiting integration."""

from collections.abc import Callable
from functools import wraps
from hashlib import sha256
from json import dumps
from logging import getLogger
from typing import Any

from app.managers.cache_manager import CacheManager

logger = getLogger(__name__)


def cached(
    cache_manager: CacheManager,
    ttl: int | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable:
    """FastAPI endpoint result caching decorator.

    Args:
        cache_manager: Cache manager instance.
        ttl: Time to live in seconds.
        namespace: Cache namespace.
        key_builder: Custom function to build cache key from args/kwargs.

    Returns:
        Decorated function.

    Example:
        @app.get("/items/{item_id}")
        @cached(cache_manager, ttl=3600, namespace="items")
        async def get_item(item_id: int) -> dict:
            return {"id": item_id, "name": "Item"}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: list[Any], **kwargs: dict[str, Any]) -> object:
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Auto-generate key from function name and arguments
                cache_key = _generate_cache_key(func.__name__, *args, **kwargs)

            # Try to get from cache
            try:
                cached_value = await cache_manager.get(cache_key, namespace)
                if cached_value is not None:
                    logger.debug(f"Cache hit for key: {cache_key}")
                    return cached_value
            except RuntimeError as e:
                logger.warning(f"Cache retrieval failed: {e}")

            # Execute function and cache result
            result = await func(*args, **kwargs)

            try:
                await cache_manager.set(
                    cache_key,
                    result,
                    ttl=ttl,
                    namespace=namespace,
                )
                logger.debug(f"Cached result for key: {cache_key}")
            except RuntimeError as e:
                logger.warning(f"Failed to cache result: {e}")

            return result

        return wrapper

    return decorator


def cache_busting(
    cache_manager: CacheManager,
    keys: list[str] | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., list[str]] | None = None,
) -> Callable:
    """Busting on mutations (POST, PUT, DELETE) cache decorator.

    Args:
        cache_manager: Cache manager instance.
        keys: List of cache keys to bust.
        namespace: Cache namespace.
        key_builder: Custom function to build keys to bust from args/kwargs.

    Returns:
        Decorated function.

    Example:
        @app.post("/items")
        @cache_busting(cache_manager, keys=["items_list"], namespace="items")
        async def create_item(item: Item) -> dict:
            return {"id": 1, "name": item.name}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: list[Any], **kwargs: dict[str, Any]) -> object:
            # Execute function
            result = await func(*args, **kwargs)

            # Determine keys to bust
            keys_to_bust = keys or []
            if key_builder:
                keys_to_bust = key_builder(*args, **kwargs)

            # Bust cache
            if keys_to_bust:
                try:
                    deleted = await cache_manager.delete(*keys_to_bust, namespace=namespace)
                    logger.debug(f"Cache busted {deleted} keys: {keys_to_bust}")
                except RuntimeError as e:
                    logger.warning(f"Cache busting failed: {e}")

            return result

        return wrapper

    return decorator


def _generate_cache_key(func_name: str, *args: list[Any], **kwargs: dict[str, Any]) -> str:
    """Generate cache key from function name and arguments.

    Args:
        func_name: Name of the function.
        *args: Function arguments.
        **kwargs: Function keyword arguments.

    Returns:
        Generated cache key.
    """

    # Filter out request objects and other non-serializable items
    serializable_args = []
    for arg in args:
        try:
            dumps(arg, default=str)
            serializable_args.append(arg)
        except (TypeError, ValueError):
            # Skip non-serializable arguments
            pass

    serializable_kwargs = {}
    for key, value in kwargs.items():
        try:
            dumps(value, default=str)
            serializable_kwargs[key] = value
        except (TypeError, ValueError):
            # Skip non-serializable values
            pass

    key_parts = [func_name]
    if serializable_args:
        key_parts.append(dumps(serializable_args, default=str, sort_keys=True))
    if serializable_kwargs:
        key_parts.append(dumps(serializable_kwargs, default=str, sort_keys=True))

    key_string = ":".join(key_parts)
    return sha256(key_string.encode()).hexdigest()[:16]
