from collections.abc import Awaitable, Callable

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
from app.monitoring import get_logger

logger = get_logger(__name__)


class AiError(BaseAppError):
    """Base exception for AI client errors."""

    def __init__(
        self,
        detail: str = "We're having trouble with our AI service. Please try again in a moment.",
    ) -> None:
        super().__init__(
            detail=detail,
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        )


class AiAuthenticationError(AiError):
    """Authentication failed."""

    def __init__(
        self,
        detail: str = "Our AI service is temporarily unavailable. Please try again later.",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_401_UNAUTHORIZED


class AiQuotaExceededError(AiError):
    """Quota exceeded."""

    def __init__(
        self,
        detail: str = "We've reached our AI service limit. Please try again in a few moments.",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_429_TOO_MANY_REQUESTS


class AiNetworkError(AiError):
    """Network connectivity issues."""

    def __init__(
        self,
        detail: str = "We're having trouble connecting to our AI service. Please try again.",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_503_SERVICE_UNAVAILABLE


class AiResponseError(AiError):
    """Invalid response format."""

    def __init__(
        self,
        detail: str = "We received an unexpected response from our AI service. Please try again.",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_502_BAD_GATEWAY


class AIGenerationError(AiError):
    """Raised when AI content generation fails."""

    def __init__(
        self,
        detail: str = "We couldn't generate the content you requested. Please try again or rephrase your request.",
    ) -> None:
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

    def __init__(
        self,
        detail: str = "We're having trouble with our AI service. Please try again in a moment.",
    ) -> None:
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

    def __init__(
        self,
        detail: str = "We couldn't create your itinerary right now. Please try again or contact us for personalized assistance.",
    ) -> None:
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


class QueryProcessingError(AiError):
    """Raised when AI query processing fails."""

    def __init__(
        self,
        detail: str = "We couldn't process your question. Please try rephrasing it or ask something else.",
    ) -> None:
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


class ContactAnalysisError(AiError):
    """Raised when AI contact analysis fails."""

    def __init__(
        self,
        detail: str = "We couldn't analyze your message. Please try again or submit your inquiry directly.",
    ) -> None:
        super().__init__(detail)
        self.status_code = HTTP_502_BAD_GATEWAY

    def __str__(self) -> str:
        return f"{self.detail}"


# Create the exception handler using the helper
ai_exception_handler: Callable[[Request, Exception], Awaitable[ORJSONResponse]] = (
    create_exception_handler(logger)
)
