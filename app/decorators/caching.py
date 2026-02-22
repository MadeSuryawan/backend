# app/decorators/caching.py
"""FastAPI decorators for caching with rate limiting integration."""

from collections.abc import Callable
from functools import wraps
from hashlib import sha256
from inspect import signature
from json import dumps
from typing import Any

from fastapi import Request
from fastapi.exceptions import ResponseValidationError
from pydantic import BaseModel, TypeAdapter, ValidationError
from redis.exceptions import RedisError

from app.context import cache_manager_ctx
from app.dependencies import get_cache_manager
from app.errors import BASE_EXCEPTION, CacheKeyError
from app.managers.cache_manager import CacheManager
from app.monitoring import get_logger, metrics

logger = get_logger(__name__)

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
    """
    Extract Request argument from function call by type.

    Searches for an argument of type Request in the bound arguments.
    This allows the parameter to be named anything (request, req, etc.).

    Parameters
    ----------
    func : Callable
        The function being decorated.
    *args : tuple
        Positional arguments passed to the function.
    **kwargs : dict
        Keyword arguments passed to the function.

    Returns
    -------
    Request
        The FastAPI Request object.

    Raises
    ------
    AttributeError
        If no Request argument is found.

    Examples
    --------
    >>> async def handler(request: Request): ...
    >>> req = get_request_arg(handler, mock_request)
    """
    try:
        bound = signature(func).bind(*args, **kwargs)
        bound.apply_defaults()

        # Search by type instead of hardcoded name
        for value in bound.arguments.values():
            if isinstance(value, Request):
                return value

        # Not found
        details = f"Request argument not found in {func.__name__} function"
        raise AttributeError(details)

    except TypeError as e:
        details = f"Cannot bind arguments for {func.__name__}: {e}"
        raise AttributeError(details) from e


def _get_cache_manager(
    func: Callable[..., Any],
    *args: list[Any],
    **kwargs: dict[str, Any],
) -> CacheManager:
    """
    Get cache manager from context or request.

    Priority:
    1. ContextVars (set by ContextMiddleware)
    2. Request object extraction
    3. Raise error if neither available

    Parameters
    ----------
    func : Callable
        The function being decorated.
    *args : tuple
        Positional arguments passed to the function.
    **kwargs : dict
        Keyword arguments passed to the function.

    Returns
    -------
    CacheManager
        The cache manager instance.

    Raises
    ------
    AttributeError
        If cache manager cannot be found.

    Examples
    --------
    >>> cache_manager = _get_cache_manager(handler, mock_request)
    """
    # Try ContextVars first
    cache_manager = cache_manager_ctx.get()
    if cache_manager is not None:
        return cache_manager

    # Fallback: extract from Request
    try:
        request = get_request_arg(func, *args, **kwargs)
        return get_cache_manager(request)
    except AttributeError as e:
        details = (
            f"Cannot get CacheManager for {func.__name__}: "
            f"not found in context and no Request argument available. "
            f"Ensure middleware is registered or pass Request to the function."
        )
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
            cache_manager = _get_cache_manager(func, *args, **kwargs)

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
                    metrics.record_cache_hit()
                    logger.debug(f"Cache hit for key: {cache_key}")

                    type_annotation = response_model or _infer_response_type_from_callable(func)
                    if type_annotation:
                        return validate_cache(cached_value, type_annotation)

                    return cached_value
            except exceptions as e:
                logger.warning(f"Cache retrieval failed: {e}")

            # Cache miss - record metric before fetching new value
            metrics.record_cache_miss()
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
            cache_manager = _get_cache_manager(func, *args, **kwargs)

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
