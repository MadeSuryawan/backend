# app/decorators/caching.py
"""FastAPI decorators for caching with rate limiting integration."""

from collections.abc import Callable
from functools import wraps
from hashlib import sha256
from inspect import signature
from json import dumps
from logging import getLogger
from typing import Any

from fastapi import Request
from fastapi.exceptions import ResponseValidationError
from pydantic import BaseModel, TypeAdapter, ValidationError
from redis.exceptions import RedisError

from app.dependencies import get_cache_manager
from app.errors import BASE_EXCEPTION, CacheKeyError
from app.managers.cache_manager import CacheManager
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


def get_request_arg(
    func: Callable[..., Any],
    *args: list[Any],
    **kwargs: dict[str, Any],
) -> Request:
    try:
        bound = signature(func).bind(*args, **kwargs)
        bound.apply_defaults()  # populates defaults if any are missing
        return bound.arguments["request"]
    except KeyError as e:
        details = f"Request argument not found on {func.__name__} function"
        raise AttributeError(details) from e


def _infer_response_type_from_callable(func: Callable[..., Any]) -> object | None:
    return func.__annotations__.get("return")


def validate_cache(value: object, type_annotation: object) -> object:
    adapter = TypeAdapter(type_annotation)
    return adapter.validate_python(value)


def _to_json_safe(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_json_safe(v) for v in value)
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, set):
        return [_to_json_safe(v) for v in value]
    return value


def cached(
    ttl: int | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., str] | None = None,
    response_model: object | None = None,
) -> Callable:
    """
    FastAPI endpoint result caching decorator.

    Args:
        ttl: Time to live in seconds.
        namespace: Cache namespace.
        key_builder: Custom function to build cache key from args/kwargs.
        response_model: Pydantic model or type to validate cached data against.
                        If None, returns the raw cached value (usually a dict).

    Returns:
        Decorated function.

    Example:
        @app.get("/items/{item_id}")
        @cached(ttl=3600, namespace="items", response_model=Item)
        async def get_item(item_id: int) -> Item:
            return Item(id=item_id, name="Item")
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: list[Any], **kwargs: dict[str, Any]) -> object:
            cache_manager = get_cache_manager(get_request_arg(func, *args, **kwargs))

            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Auto-generate key from function name and arguments
                cache_key = _generate_cache_key(func.__name__, *args, **kwargs)
            # Try to get from cache
            try:
                skip = bool(kwargs.get("refresh", False))
                if not skip and (cached_value := await cache_manager.get(cache_key, namespace)):
                    logger.debug(f"Cache hit for key: {cache_key}")

                    type_annotation = response_model or _infer_response_type_from_callable(func)
                    if type_annotation:
                        return validate_cache(cached_value, type_annotation)

                    return cached_value
            except exceptions as e:
                logger.warning(f"Cache retrieval failed: {e}")

            return await cache_new_value(
                func,
                cache_manager,
                cache_key,
                ttl,
                namespace,
                *args,
                **kwargs,
            )

        return wrapper

    return decorator


async def cache_new_value(
    func: Callable,
    cache_manager: CacheManager,
    cache_key: str,
    ttl: int | None = None,
    namespace: str | None = None,
    *args: list[Any],
    **kwargs: dict[str, Any],
) -> object:
    result = await func(*args, **kwargs)
    # logger.debug(f"{result=}, {type(result)=}")

    try:
        payload = _to_json_safe(result)
        if await cache_manager.set(
            cache_key,
            payload,
            ttl=ttl,
            namespace=namespace,
        ):
            logger.debug(f"Cached result for key: {cache_key}")
            return result
    except exceptions as e:
        logger.warning(f"{e}")

    return result


def cache_busting(
    keys: list[str] | None = None,
    namespace: str | None = None,
    key_builder: Callable[..., list[str]] | None = None,
) -> Callable:
    """
    Busting on mutations (POST, PUT, DELETE) cache decorator.

    Args:
        keys: List of cache keys to bust.
        namespace: Cache namespace.
        key_builder: Custom function to build keys to bust from args/kwargs.

    Returns:
        Decorated function.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: list[Any], **kwargs: dict[str, Any]) -> object:
            cache_manager = get_cache_manager(get_request_arg(func, *args, **kwargs))

            # Execute function
            result = await func(*args, **kwargs)

            # Determine keys to bust
            keys_to_bust = keys or []
            if key_builder:
                keys_to_bust = key_builder(*args, **kwargs)
            # Bust cache
            if keys_to_bust:
                try:
                    if deleted := await cache_manager.delete(*keys_to_bust, namespace=namespace):
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
