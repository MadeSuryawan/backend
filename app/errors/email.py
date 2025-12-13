from logging import getLogger

from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_502_BAD_GATEWAY,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from app.errors import BaseAppError, create_exception_handler
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class EmailServiceError(BaseAppError):
    """Base class for all email service related errors."""

    def __init__(self, detail: str = "Email service error") -> None:
        super().__init__(
            detail=detail,
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ConfigurationError(EmailServiceError):
    """Raised when files (secrets/tokens) are missing."""

    def __init__(self, detail: str = "Email service configuration error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_503_SERVICE_UNAVAILABLE


class AuthenticationError(EmailServiceError):
    """Raised when OAuth2 token refresh fails."""

    def __init__(self, detail: str = "Email service authentication error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_401_UNAUTHORIZED


class SendingError(EmailServiceError):
    """Raised when the Google API fails to send the message."""

    def __init__(self, detail: str = "Email service sending error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_502_BAD_GATEWAY


class NetworkError(EmailServiceError):
    """Raised when network connectivity issues occur."""

    def __init__(self, detail: str = "Email service network error") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = HTTP_503_SERVICE_UNAVAILABLE


# Create the exception handler using the helper
email_client_exception_handler = create_exception_handler(logger)
