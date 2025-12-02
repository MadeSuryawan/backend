from collections.abc import Awaitable, Callable
from logging import Logger

from fastapi import Request
from fastapi.responses import ORJSONResponse
from starlette import status

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
        msg: str = "Internal Server Error",
        error_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        self.msg = msg
        self.error_code = error_code

    def __str__(self) -> str:
        return self.msg


def create_exception_handler(
    logger: Logger,
) -> Callable[[Request, Exception], Awaitable[ORJSONResponse]]:
    """
    Create a standardized exception handler for the application.

    Args:
        logger: Logger instance to use for logging exceptions.
        limiter: Boolean flag to indicate if rate limiter is enabled.

    Returns:
        A callable exception handler.
    """

    async def handler(request: Request, exc: Exception) -> ORJSONResponse:
        host = request.client.host if request.client else "unknown"

        # Default values
        error_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        msg = "Internal Server Error"

        # Extract from custom exception if available
        if hasattr(exc, "error_code"):
            error_code = exc.error_code
        if hasattr(exc, "msg"):
            msg = exc.msg

        logger.warning(f"{msg} for ip: {host} for endpoint {request.url.path}")

        # Build response content with msg and any additional exception attributes
        content = {"detail": msg}
        content.update({k: v for k, v in exc.__dict__.items() if k not in ("error_code", "msg")})

        return ORJSONResponse(content=content, status_code=error_code)

    return handler
