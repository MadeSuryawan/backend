"""Idempotency-related error classes."""

from collections.abc import Awaitable, Callable
from logging import getLogger

from fastapi import Request
from fastapi.responses import ORJSONResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_409_CONFLICT, HTTP_500_INTERNAL_SERVER_ERROR

from app.errors.base import BaseAppError
from app.utils.helpers import file_logger, host

logger = file_logger(getLogger(__name__))


class IdempotencyError(BaseAppError):
    """Base class for idempotency errors."""

    def __init__(
        self,
        detail: str = "Idempotency error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(detail=detail, status_code=status_code)


class DuplicateRequestError(IdempotencyError):
    """Raised when a duplicate request is detected that is still processing."""

    def __init__(
        self,
        idempotency_key: str,
        retry_after: float = 5.0,
    ) -> None:
        self.idempotency_key = idempotency_key
        self.retry_after = retry_after
        super().__init__(
            detail=f"Request with key '{idempotency_key}' is already being processed",
            status_code=HTTP_409_CONFLICT,
        )


class IdempotencyKeyMissingError(IdempotencyError):
    """Raised when idempotency key is required but not provided."""

    def __init__(self) -> None:
        super().__init__(
            detail="Idempotency-Key header is required for this endpoint",
            status_code=HTTP_400_BAD_REQUEST,
        )


class IdempotencyKeyInvalidError(IdempotencyError):
    """Raised when idempotency key format is invalid."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(
            detail=f"Invalid idempotency key format: '{key}'. Must be a valid UUID.",
            status_code=HTTP_400_BAD_REQUEST,
        )


class IdempotencyStorageError(IdempotencyError):
    """Raised when there's an error storing or retrieving idempotency data."""

    def __init__(self, operation: str, detail: str | None = None) -> None:
        self.operation = operation
        msg = f"Idempotency storage error during {operation}"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(detail=msg, status_code=HTTP_500_INTERNAL_SERVER_ERROR)


def idempotency_exception_handler() -> (
    Callable[[Request, IdempotencyError], Awaitable[ORJSONResponse]]
):
    """
    Create exception handler for idempotency errors.

    Returns:
        A callable exception handler for IdempotencyError.
    """

    async def handler(request: Request, exc: IdempotencyError) -> ORJSONResponse:
        logger.warning(
            f"Idempotency error: {exc.detail} for ip: {host(request)} "
            f"for endpoint {request.url.path}",
        )

        content: dict[str, str | float] = {"detail": exc.detail}

        # Add retry_after header for duplicate request errors
        headers: dict[str, str] = {}
        if isinstance(exc, DuplicateRequestError):
            content["idempotency_key"] = exc.idempotency_key
            content["retry_after"] = exc.retry_after
            headers["Retry-After"] = str(int(exc.retry_after))

        return ORJSONResponse(
            content=content,
            status_code=exc.status_code,
            headers=headers if headers else None,
        )

    return handler
