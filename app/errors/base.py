from collections.abc import Awaitable, Callable
from logging import Logger

from fastapi import Request
from fastapi.responses import ORJSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.utils.helpers import host

BASE_EXCEPTION = (
    OSError,
    PermissionError,
    MemoryError,
    RuntimeError,
    ConnectionError,
    TimeoutError,
)


class BaseAppError(Exception):
    """Base exception class for application errors."""

    def __init__(
        self,
        detail: str = "Internal Server Error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        self.detail = detail
        self.status_code = status_code

    def __str__(self) -> str:
        return self.detail


def create_exception_handler(
    logger: Logger,
) -> Callable[[Request, Exception], Awaitable[ORJSONResponse]]:
    """
    Create a standardized exception handler for the application.

    Args:
        logger: Logger instance to use for logging exceptions.

    Returns:
        A callable exception handler.
    """

    async def handler(request: Request, exc: Exception) -> ORJSONResponse:
        # Default values
        status_code = HTTP_500_INTERNAL_SERVER_ERROR
        detail = "Internal Server Error"

        # Extract from custom exception if available
        if hasattr(exc, "status_code"):
            status_code = exc.status_code
        if hasattr(exc, "detail"):
            detail = exc.detail

        logger.warning(f"{detail} for ip: {host(request)} for endpoint {request.url.path}")

        # Build response content with msg and any additional exception attributes
        content = {"detail": detail}
        content.update(
            {k: v for k, v in exc.__dict__.items() if k not in ("status_code", "detail")},
        )

        return ORJSONResponse(content=content, status_code=status_code)

    return handler
