"""Custom validation error handling for FastAPI."""

from logging import getLogger
from typing import cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import ORJSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT

from app.errors import BaseAppError
from app.utils.helpers import file_logger, host

logger = file_logger(getLogger(__name__))


class ValidationError(BaseAppError):
    """Custom validation error class."""

    def __init__(
        self,
        detail: str = "Validation Error",
        errors: list[dict] | None = None,
    ) -> None:
        super().__init__(detail=detail, status_code=HTTP_422_UNPROCESSABLE_CONTENT)
        self.errors = errors or []


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> ORJSONResponse:
    """
    Handle Pydantic validation errors with cleaner response format.

    Args:
        request: The incoming request.
        exc: The RequestValidationError exception.

    Returns:
        ORJSONResponse with formatted validation errors.
    """
    exec_error = cast(RequestValidationError, exc)

    # Format errors for cleaner response
    formatted_errors = []
    for error in exec_error.errors():
        formatted_error = {
            "field": ".".join(str(loc) for loc in error.get("loc", [])[1:]),  # Skip 'body'
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "validation_error"),
        }
        # Include input value if available (useful for debugging)
        if "input" in error:
            formatted_error["input"] = error["input"]
        # Include context if available (e.g., max_length, min_length)
        # Convert non-serializable values (like ValueError) to strings
        if "ctx" in error:
            ctx = error["ctx"]
            serializable_ctx = {}
            for key, value in ctx.items():
                if isinstance(value, Exception):
                    serializable_ctx[key] = str(value)
                else:
                    serializable_ctx[key] = value
            formatted_error["context"] = serializable_ctx
        formatted_errors.append(formatted_error)

    logger.warning(
        f"Validation error for ip: {host(request)} at endpoint {request.url.path}: {formatted_errors}",
    )

    return ORJSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": "Validation failed",
            "errors": formatted_errors,
        },
    )
