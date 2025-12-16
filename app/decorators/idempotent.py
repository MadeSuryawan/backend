"""Idempotency decorator for FastAPI endpoints."""

from collections.abc import Awaitable, Callable
from functools import wraps
from logging import getLogger
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel

from app.errors.idempotency import IdempotencyKeyInvalidError, IdempotencyKeyMissingError
from app.managers.idempotency_manager import IdempotencyManager
from app.schemas.idempotency import IdempotencyStatus
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

# Type variables for decorator
P = ParamSpec("P")
T = TypeVar("T")

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"


def _validate_uuid(key: str) -> UUID:
    """
    Validate and parse UUID from string.

    Args:
        key: String to validate as UUID

    Returns:
        Parsed UUID

    Raises:
        IdempotencyKeyInvalidError: If key is not a valid UUID
    """
    try:
        return UUID(key)
    except ValueError as e:
        raise IdempotencyKeyInvalidError(key) from e


def _extract_idempotency_key(
    request: Request,
    *,
    required: bool = True,
) -> UUID | None:
    """
    Extract idempotency key from request header.

    Args:
        request: FastAPI request object
        required: Whether the key is required

    Returns:
        Parsed UUID or None if not required and missing

    Raises:
        IdempotencyKeyMissingError: If required and missing
        IdempotencyKeyInvalidError: If present but invalid format
    """
    key = request.headers.get(IDEMPOTENCY_KEY_HEADER)

    if not key:
        if required:
            raise IdempotencyKeyMissingError
        return None

    return _validate_uuid(key)


def _serialize_response(response: Any) -> Any:
    """
    Serialize response for caching.

    Converts Pydantic models and collections to JSON-serializable format.

    Args:
        response: Response object to serialize

    Returns:
        JSON-serializable representation
    """
    if isinstance(response, BaseModel):
        return response.model_dump()
    if isinstance(response, list):
        return [_serialize_response(item) for item in response]
    if isinstance(response, dict):
        return {k: _serialize_response(v) for k, v in response.items()}
    return response


def idempotent(
    idempotency_manager: IdempotencyManager,
    namespace: str,
    *,
    required: bool = True,
    response_model: type[BaseModel] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """
    Decorator for making endpoints idempotent.

    This decorator intercepts requests and checks for an Idempotency-Key header.
    If found, it:
    1. Checks if a response already exists for that key
    2. If completed, returns the cached response
    3. If processing, raises DuplicateRequestError
    4. If failed or not found, executes the handler and caches the result

    Args:
        idempotency_manager: IdempotencyManager instance
        namespace: Namespace for the idempotency key (e.g., 'auth:register')
        required: Whether idempotency key is required (default: True)
        response_model: Pydantic model for deserializing cached responses

    Returns:
        Decorated function

    Example:
        ```python
        @router.post("/register")
        @idempotent(idempotency_manager, namespace="auth:register")
        async def register(request: Request, ...):
            ...
        ```
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Extract request from args or kwargs
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if not request:
                request = kwargs.get("request")

            if not request:
                # No request object, execute normally (shouldn't happen in FastAPI)
                logger.warning("No Request object found, executing without idempotency")
                return await func(*args, **kwargs)

            # Extract idempotency key
            idempotency_key = _extract_idempotency_key(request, required=required)

            if not idempotency_key:
                # Key not required and not provided, execute normally
                return await func(*args, **kwargs)

            # Check for existing record
            existing = await idempotency_manager.check_and_set_processing(
                namespace=namespace,
                idempotency_key=idempotency_key,
            )

            if existing:
                # Return cached response for completed requests
                if existing.status == IdempotencyStatus.COMPLETED:
                    logger.debug(f"Returning cached response for key: {idempotency_key}")
                    if response_model and existing.response:
                        return response_model.model_validate(existing.response)
                    return existing.response
                # FAILED status allows retry - proceed with execution
                # (check_and_set_processing returns None for failed records)

            try:
                # Execute the handler
                result = await func(*args, **kwargs)

                # Store successful response
                serialized = _serialize_response(result)
                await idempotency_manager.set_completed(
                    namespace=namespace,
                    idempotency_key=idempotency_key,
                    response=serialized,
                )

                return result

            except Exception as e:
                # Store failure (allows retry with same key)
                await idempotency_manager.set_failed(
                    namespace=namespace,
                    idempotency_key=idempotency_key,
                    error=str(e),
                )
                raise

        return wrapper

    return decorator


def idempotent_inline(
    idempotency_manager: IdempotencyManager,
    namespace: str,
    idempotency_key: str | UUID | None,
    response_model: type[BaseModel] | None = None,
) -> "IdempotencyContext":
    """
    Create an idempotency context for inline use (non-decorator pattern).

    This allows using idempotency in endpoints where you want more control
    over the flow or can't use a decorator.

    Args:
        idempotency_manager: IdempotencyManager instance
        namespace: Namespace for the idempotency key
        idempotency_key: The idempotency key (None to skip idempotency)
        response_model: Pydantic model for deserializing cached responses

    Returns:
        IdempotencyContext for use with async context manager

    Example:
        ```python
        @router.post("/register")
        async def register(request: Request, ...):
            key = request.headers.get("Idempotency-Key")
            async with idempotent_inline(manager, "auth:register", key) as ctx:
                if ctx.cached_response:
                    return ctx.cached_response
                result = await create_user(...)
                ctx.set_response(result)
                return result
        ```
    """
    return IdempotencyContext(
        manager=idempotency_manager,
        namespace=namespace,
        idempotency_key=idempotency_key,
        response_model=response_model,
    )


class IdempotencyContext:
    """
    Context manager for inline idempotency handling.

    Provides a more flexible alternative to the decorator pattern.
    """

    __slots__ = (
        "_cached",
        "_completed",
        "_key",
        "_manager",
        "_namespace",
        "_response_model",
    )

    def __init__(
        self,
        manager: IdempotencyManager,
        namespace: str,
        idempotency_key: str | UUID | None,
        response_model: type[BaseModel] | None = None,
    ) -> None:
        self._manager = manager
        self._namespace = namespace
        self._key = str(idempotency_key) if idempotency_key else None
        self._response_model = response_model
        self._cached: Any = None
        self._completed = False

    @property
    def cached_response(self) -> Any:
        """Get cached response if available."""
        return self._cached

    @property
    def has_cached(self) -> bool:
        """Check if a cached response is available."""
        return self._cached is not None

    async def __aenter__(self) -> "IdempotencyContext":
        """Enter the context, checking for existing response."""
        if not self._key:
            return self

        existing = await self._manager.check_and_set_processing(
            namespace=self._namespace,
            idempotency_key=self._key,
        )

        if existing and existing.status == IdempotencyStatus.COMPLETED:
            if self._response_model and existing.response:
                self._cached = self._response_model.model_validate(existing.response)
            else:
                self._cached = existing.response

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the context, handling success/failure."""
        if not self._key:
            return

        if exc_val is not None:
            # Store failure
            await self._manager.set_failed(
                namespace=self._namespace,
                idempotency_key=self._key,
                error=str(exc_val),
            )
        elif not self._completed and not self._cached:
            # No response was set and no exception - treat as incomplete
            logger.warning(
                f"Idempotency context exited without setting response for key: {self._key}",
            )

    async def set_response(self, response: Any) -> None:
        """
        Set the successful response to cache.

        Args:
            response: Response to cache
        """
        if not self._key:
            return

        serialized = _serialize_response(response)
        await self._manager.set_completed(
            namespace=self._namespace,
            idempotency_key=self._key,
            response=serialized,
        )
        self._completed = True
