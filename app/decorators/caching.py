# app/decorators/caching.py
"""FastAPI decorators for caching with rate limiting integration."""

from collections.abc import Callable
from functools import wraps
from hashlib import sha256
from json import dumps
from logging import getLogger
from typing import TYPE_CHECKING, Any

from fastapi.exceptions import ResponseValidationError
from pydantic import TypeAdapter, ValidationError
from redis.exceptions import RedisError

from app.configs import file_logger
from app.errors import BASE_EXCEPTION, CacheKeyError

if TYPE_CHECKING:
    from app.managers.cache_manager import CacheManager

logger = file_logger(getLogger(__name__))

exceptions = (
    RedisError,
    CacheKeyError,
    *BASE_EXCEPTION,
    ValidationError,
    ResponseValidationError,
    TypeError,
)


def validate_response(value: object, response_type: Any) -> object | None:  # noqa: ANN401
    """
    Validate response against Pydantic models or types.

    Uses TypeAdapter to handle Pydantic Models, lists, dicts, etc.
    """
    logger.info(f"Validating Value against {response_type}")
    try:
        adapter = TypeAdapter(response_type)
        valid = adapter.validate_python(value)
    except exceptions as e:
        logger.warning(f"Validation failed: {e}")
        mssg = f"Could not validate cache against {response_type}"
        raise ValidationError(mssg) from e
    return valid


def cached(
    cache_manager: "CacheManager",
    ttl: int | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
    response_model: Any = None,  # noqa: ANN401
) -> Callable:
    """
    FastAPI endpoint result caching decorator.

    Args:
        cache_manager: Cache manager instance.
        ttl: Time to live in seconds.
        namespace: Cache namespace.
        key_builder: Custom function to build cache key from args/kwargs.
        response_model: Pydantic model or type to validate cached data against.
                        If None, returns the raw cached value (usually a dict).

    Returns:
        Decorated function.

    Example:
        @app.get("/items/{item_id}")
        @cached(cache_manager, ttl=3600, namespace="items", response_model=Item)
        async def get_item(item_id: int) -> Item:
            return Item(id=item_id, name="Item")
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
                if cached_value := await cache_manager.get(cache_key, namespace):
                    logger.debug(f"Cache hit for key: {cache_key}")

                    # Validate and convert if a model is provided
                    if response_model:
                        return validate_response(cached_value, response_model)

                    # Otherwise return raw data (dict/json)
                    return cached_value
            except exceptions as e:
                logger.warning(f"Cache retrieval failed: {e}")

            # Execute function and cache result
            result = await func(*args, **kwargs)
            # logger.debug(f"{result=}, {type(result)=}")

            try:
                if await cache_manager.set(
                    cache_key,
                    result,
                    ttl=ttl,
                    namespace=namespace,
                ):
                    logger.debug(f"Cached result for key: {cache_key}")
                    return result
            except exceptions as e:
                logger.warning(f"{e}")

            return result

        return wrapper

    return decorator


def cache_busting(
    cache_manager: "CacheManager",
    keys: list[str] | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., list[str]] | None = None,
) -> Callable:
    """
    Busting on mutations (POST, PUT, DELETE) cache decorator.

    Args:
        cache_manager: Cache manager instance.
        keys: List of cache keys to bust.
        namespace: Cache namespace.
        key_builder: Custom function to build keys to bust from args/kwargs.

    Returns:
        Decorated function.
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
                except exceptions as e:
                    logger.warning(f"Cache busting failed: {e}")

            return result

        return wrapper

    return decorator


def _generate_cache_key(func_name: str, *args: list[Any], **kwargs: dict[str, Any]) -> str:
    """
    Generate cache key from function name and arguments.

    Args:
        func_name: Name of the function.
        *args: Function arguments.
        **kwargs: Function keyword arguments.

    Returns:
        Generated cache key.
    """
    key_parts = [func_name]

    # Process args
    for arg in args:
        try:
            key_parts.append(dumps(arg, default=str, sort_keys=True))
        except (TypeError, ValueError):
            logger.warning(f"Argument {arg} is not serializable, skipping for cache key.")

    # Process kwargs
    if kwargs:
        try:
            key_parts.append(dumps(kwargs, default=str, sort_keys=True))
        except (TypeError, ValueError):
            # Fallback for kwargs if full dict fails
            safe_kwargs = {}
            for k, v in kwargs.items():
                try:
                    dumps(v, default=str, sort_keys=True)
                    safe_kwargs[k] = v
                except (TypeError, ValueError):
                    logger.warning(f"Keyword argument {k}={v} is not serializable, skipping.")
            key_parts.append(dumps(safe_kwargs, default=str, sort_keys=True))

    key_string = ":".join(key_parts)
    return sha256(key_string.encode()).hexdigest()[:16]
