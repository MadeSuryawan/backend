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
        super().__init__(
            "Oops! The email/username or password you entered doesn't match our records. Please try again.",
            HTTP_401_UNAUTHORIZED,
        )


class OAuthError(UserAuthenticationError):
    """Raised when OAuth authentication fails."""

    def __init__(self, message: str = "OAuth authentication failed") -> None:
        super().__init__(
            "We couldn't complete your sign-in with the selected provider. Please try again or use a different sign-in method.",
            HTTP_400_BAD_REQUEST,
        )


class OAuthStateError(UserAuthenticationError):
    """Raised when OAuth state validation fails (CSRF protection)."""

    def __init__(self, message: str = "Invalid or expired OAuth state") -> None:
        super().__init__(
            "For your security, this sign-in attempt couldn't be verified. The session may have expired - please try signing in again.",
            HTTP_400_BAD_REQUEST,
        )


class AccountLockedError(UserAuthenticationError):
    """Raised when account is locked due to too many failed login attempts."""

    def __init__(self, seconds_remaining: int = 0) -> None:
        minutes = seconds_remaining // 60
        detail = (
            f"Your account is temporarily locked for security reasons after multiple failed login attempts. "
            f"Please try again in {minutes} minute{'s' if minutes != 1 else ''} or reset your password if you've forgotten it."
        )
        super().__init__(detail, HTTP_429_TOO_MANY_REQUESTS)
        self.seconds_remaining = seconds_remaining


class InvalidTokenError(UserAuthenticationError):
    """Raised when token is invalid or revoked."""

    def __init__(self) -> None:
        super().__init__(
            "Your session has expired or is no longer valid. Please sign in again to continue.",
            HTTP_401_UNAUTHORIZED,
        )


class InvalidRefreshTokenError(UserAuthenticationError):
    """Raised when refresh token is invalid."""

    def __init__(self) -> None:
        super().__init__(
            "Your session has expired. Please sign in again to continue.", HTTP_401_UNAUTHORIZED,
        )


class TokenRevokedError(UserAuthenticationError):
    """Raised when token has been revoked."""

    def __init__(self) -> None:
        super().__init__(
            "Your session has been signed out. Please sign in again to continue.",
            HTTP_401_UNAUTHORIZED,
        )


class TokenExpiredError(UserAuthenticationError):
    """Raised when token has expired."""

    def __init__(self) -> None:
        super().__init__(
            "Your session has expired for security reasons. Please sign in again to continue.",
            HTTP_401_UNAUTHORIZED,
        )


class UserDeactivatedError(UserAuthenticationError):
    """Raised when user account is deactivated."""

    def __init__(self) -> None:
        super().__init__(
            "This account has been deactivated. Please contact support if you believe this is an error.",
            HTTP_401_UNAUTHORIZED,
        )


class EmailVerificationError(UserAuthenticationError):
    """Raised when email verification fails."""

    def __init__(self) -> None:
        super().__init__(
            "This verification link is invalid or has expired. Please request a new verification email to try again.",
            HTTP_401_UNAUTHORIZED,
        )


class VerificationTokenUsedError(UserAuthenticationError):
    """Raised when verification token has already been used."""

    def __init__(self) -> None:
        super().__init__(
            "This verification link has already been used. Your email may already be verified - try signing in. If you're still having trouble, request a new verification email.",
            HTTP_401_UNAUTHORIZED,
        )


class ResetTokenUsedError(UserAuthenticationError):
    """Raised when password reset token has already been used."""

    def __init__(self) -> None:
        super().__init__(
            "This password reset link has already been used. For security reasons, each link can only be used once. Please request a new password reset email if you still need to reset your password.",
            HTTP_401_UNAUTHORIZED,
        )


class PasswordResetError(UserAuthenticationError):
    """Raised when password reset fails."""

    def __init__(self) -> None:
        super().__init__(
            "This password reset link is invalid or has expired. For your security, reset links expire after a limited time. Please request a new password reset email.",
            HTTP_401_UNAUTHORIZED,
        )


class PasswordChangeError(UserAuthenticationError):
    """Raised when password change fails due to invalid current password or validation error."""

    def __init__(self) -> None:
        super().__init__(
            "We couldn't change your password. Please make sure your current password is correct and that your new password meets our security requirements.",
            HTTP_400_BAD_REQUEST,
        )


class UserNotFoundError(BaseAppError):
    """Raised when user is not found."""

    def __init__(self) -> None:
        super().__init__(
            "We couldn't find a user with this information. Please check your details and try again.",
            HTTP_404_NOT_FOUND,
        )


class UserNotVerifiedError(BaseAppError):
    """Raised when user email is not verified."""

    def __init__(self) -> None:
        super().__init__(
            "Your email address hasn't been verified yet. Please check your inbox for a verification email or request a new one to unlock your account.",
            HTTP_403_FORBIDDEN,
        )


class InsufficientPermissionsError(BaseAppError):
    """Raised when user doesn't have required permissions."""

    def __init__(self, required_role: str = "admin") -> None:
        super().__init__(
            f"Sorry, you don't have permission to access this feature. This area is reserved for {required_role} users only.",
            HTTP_403_FORBIDDEN,
        )


auth_exception_handler = create_exception_handler(logger)
