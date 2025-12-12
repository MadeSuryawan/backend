"""Authentication errors."""

from logging import getLogger

from starlette.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED

from app.configs import file_logger
from app.errors.base import BaseAppError, create_exception_handler

logger = file_logger(getLogger(__name__))


class UserAuthenticationError(BaseAppError):
    """Base class for authentication errors."""

    def __init__(
        self,
        detail: str = "Authentication failed",
        status_code: int = HTTP_401_UNAUTHORIZED,
    ) -> None:
        super().__init__(detail, status_code)


class InvalidCredentialsError(UserAuthenticationError):
    """Raised when credentials are invalid."""

    def __init__(self) -> None:
        super().__init__("Invalid username or password", HTTP_401_UNAUTHORIZED)


class OAuthError(UserAuthenticationError):
    """Raised when OAuth authentication fails."""

    def __init__(self, message: str = "OAuth authentication failed") -> None:
        super().__init__(message, HTTP_400_BAD_REQUEST)


auth_exception_handler = create_exception_handler(logger)
