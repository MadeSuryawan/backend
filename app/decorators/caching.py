"""FastAPI decorators for caching with rate limiting integration."""

from collections.abc import Callable
from contextlib import suppress
from functools import wraps
from hashlib import sha256
from json import JSONDecodeError, dumps
from logging import getLogger
from typing import Any

from fastapi.exceptions import ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from redis.exceptions import RedisError
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.errors.exceptions import BASE_EXCEPTION, CacheKeyError
from app.managers.cache_manager import CacheManager
from app.schemas.items import Item, ItemUpdate
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

exceptions = (
    RedisError,
    CacheKeyError,
    *BASE_EXCEPTION,
    ValidationError,
    ResponseValidationError,
    TypeError,
)


def validate_response(value: object) -> object | None:
    """Validate response against Pydantic models."""
    logger.info("Validating Value")
    try:
        valid = Item.model_validate(value)
    except exceptions as e:
        # logger.info(type(e.errors(include_url=False)[0]))
        # return JSONResponse(
        #     status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        #     # content={"detail": e.errors(include_url=False)},
        #     content={"detail": e},
        # )
        raise ValidationError() from e
    return valid


def cached(
    cache_manager: CacheManager,
    ttl: int | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
) -> Callable:
    """
    FastAPI endpoint result caching decorator.

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
                if cached_value := await cache_manager.get(cache_key, namespace):
                    logger.debug(f"Cache hit for key: {cache_key}")
                    # return validate_response(cached_value)
                    return cached_value
            except exceptions as e:
                logger.warning(f"Cache retrieval failed: {e}")
                # return JSONResponse(
                #     status_code=HTTP_500_INTERNAL_SERVER_ERROR,
                #     content={"detail": e.errors(include_url=False)},
                # )

            # Execute function and cache result
            result: Item | dict = await func(*args, **kwargs)
            logger.debug(f"{result=}, {type(result)=}")

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
    cache_manager: CacheManager,
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

    # Filter out request objects and other non-serializable items
    with suppress(TypeError, ValueError, JSONDecodeError):
        # Skip non-serializable arguments
        serializable_args = [dumps(arg, default=str, sort_keys=True) for arg in args]

    with suppress(TypeError, ValueError):
        # Skip non-serializable keyword arguments
        serializable_kwargs = {
            key: value
            for key, value in kwargs.items()
            if isinstance(value, (str, int, float, bool))
        }

    key_parts = [func_name]
    if serializable_args:
        key_parts.append(dumps(serializable_args, default=str, sort_keys=True))
    if serializable_kwargs:
        key_parts.append(dumps(serializable_kwargs, default=str, sort_keys=True))

    key_string = ":".join(key_parts)
    return sha256(key_string.encode()).hexdigest()[:16]
