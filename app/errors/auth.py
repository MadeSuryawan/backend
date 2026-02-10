"""Authentication errors."""

from logging import getLogger

from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_429_TOO_MANY_REQUESTS,
)

from app.errors.base import BaseAppError, create_exception_handler
from app.utils.helpers import file_logger

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


class AccountLockedError(UserAuthenticationError):
    """Raised when account is locked due to too many failed login attempts."""

    def __init__(self, seconds_remaining: int = 0) -> None:
        minutes = seconds_remaining // 60
        detail = f"Account locked. Try again in {minutes} minutes."
        super().__init__(detail, HTTP_429_TOO_MANY_REQUESTS)
        self.seconds_remaining = seconds_remaining


class InvalidTokenError(UserAuthenticationError):
    """Raised when token is invalid or revoked."""

    def __init__(self) -> None:
        super().__init__("Invalid or expired token", HTTP_401_UNAUTHORIZED)


class InvalidRefreshTokenError(UserAuthenticationError):
    """Raised when refresh token is invalid."""

    def __init__(self) -> None:
        super().__init__("Invalid refresh token", HTTP_401_UNAUTHORIZED)


class TokenRevokedError(UserAuthenticationError):
    """Raised when token has been revoked."""

    def __init__(self) -> None:
        super().__init__("Token has been revoked", HTTP_401_UNAUTHORIZED)


class TokenExpiredError(UserAuthenticationError):
    """Raised when token has expired."""

    def __init__(self) -> None:
        super().__init__("Token has expired", HTTP_401_UNAUTHORIZED)


class UserDeactivatedError(UserAuthenticationError):
    """Raised when user account is deactivated."""

    def __init__(self) -> None:
        super().__init__("User account is deactivated", HTTP_401_UNAUTHORIZED)


class EmailVerificationError(UserAuthenticationError):
    """Raised when email verification fails."""

    def __init__(self) -> None:
        super().__init__("Invalid or expired verification token", HTTP_401_UNAUTHORIZED)


class VerificationTokenUsedError(UserAuthenticationError):
    """Raised when verification token has already been used."""

    def __init__(self) -> None:
        super().__init__("Verification token has already been used", HTTP_401_UNAUTHORIZED)


class PasswordResetError(UserAuthenticationError):
    """Raised when password reset fails."""

    def __init__(self) -> None:
        super().__init__("Invalid or expired reset token", HTTP_401_UNAUTHORIZED)


class PasswordChangeError(UserAuthenticationError):
    """Raised when password change fails due to invalid current password or validation error."""

    def __init__(self) -> None:
        super().__init__("Failed to change password. Please verify your current password.", HTTP_400_BAD_REQUEST)


class UserNotFoundError(BaseAppError):
    """Raised when user is not found."""

    def __init__(self) -> None:
        super().__init__("User not found", HTTP_404_NOT_FOUND)


class UserNotVerifiedError(BaseAppError):
    """Raised when user email is not verified."""

    def __init__(self) -> None:
        super().__init__("Email not verified. Please verify your email first.", HTTP_403_FORBIDDEN)


class InsufficientPermissionsError(BaseAppError):
    """Raised when user doesn't have required permissions."""

    def __init__(self, required_role: str = "admin") -> None:
        super().__init__(
            f"Insufficient permissions. Required role: {required_role}",
            HTTP_403_FORBIDDEN,
        )


auth_exception_handler = create_exception_handler(logger)
