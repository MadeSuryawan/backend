from collections.abc import Awaitable, Callable
from logging import getLogger

from fastapi.responses import ORJSONResponse
from starlette.requests import Request
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_502_BAD_GATEWAY,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.errors.base import BaseAppError, create_exception_handler
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class AiError(BaseAppError):
    """Base exception for AI client errors."""

    def __init__(self, detail: str = "AI client error") -> None:
        super().__init__(
            detail=detail,
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        )


class AiAuthenticationError(AiError):
    """Authentication failed."""

    def __init__(self, detail: str = "AI authentication failed") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_401_UNAUTHORIZED


class AiQuotaExceededError(AiError):
    """Quota exceeded."""

    def __init__(self, detail: str = "AI quota exceeded") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_429_TOO_MANY_REQUESTS


class AiNetworkError(AiError):
    """Network connectivity issues."""

    def __init__(self, detail: str = "AI network error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_503_SERVICE_UNAVAILABLE


class AiResponseError(AiError):
    """Invalid response format."""

    def __init__(self, detail: str = "Invalid AI response") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_502_BAD_GATEWAY


class AIGenerationError(AiError):
    """Raised when AI content generation fails."""

    def __init__(self, detail: str = "AI content generation failed") -> None:
        """
        Initialize AIGenerationError.

        Args:
            detail: Error message describing the failure

        """
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


class AIClientError(AiError):
    """Raised when the AI client encounters transport or protocol errors."""

    def __init__(self, detail: str = "AI client error") -> None:
        """
        Initialize AIClientError with optional causal exception.

        Args:
            detail: Error message describing the client failure
            original_error: The original exception that caused this error
        """
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY


class ItineraryGenerationError(AiError):
    """Raised when AI itinerary generation fails."""

    def __init__(self, detail: str = "AI itinerary generation failed") -> None:
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


class QueryProcessingError(AiError):
    """Raised when AI query processing fails."""

    def __init__(self, detail: str = "AI query processing failed") -> None:
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


class ContactAnalysisError(AiError):
    """Raised when AI contact analysis fails."""

    def __init__(self, detail: str = "AI contact analysis failed") -> None:
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


# Create the exception handler using the helper
ai_exception_handler: Callable[[Request, Exception], Awaitable[ORJSONResponse]] = (
    create_exception_handler(logger)
)
