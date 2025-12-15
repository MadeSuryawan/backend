"""Tests for authentication error classes."""

from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_429_TOO_MANY_REQUESTS,
)

from app.errors.auth import (
    AccountLockedError,
    EmailVerificationError,
    InsufficientPermissionsError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidTokenError,
    PasswordResetError,
    TokenExpiredError,
    TokenRevokedError,
    UserDeactivatedError,
    UserNotFoundError,
    UserNotVerifiedError,
)


class TestInvalidCredentialsError:
    """Test cases for InvalidCredentialsError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = InvalidCredentialsError()

        assert error.detail == "Invalid username or password"
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestAccountLockedError:
    """Test cases for AccountLockedError."""

    def test_message_includes_minutes(self) -> None:
        """Test that message includes lockout duration in minutes."""
        error = AccountLockedError(seconds_remaining=900)  # 15 minutes

        assert "15 minutes" in error.detail
        assert error.status_code == HTTP_429_TOO_MANY_REQUESTS
        assert error.seconds_remaining == 900

    def test_zero_seconds(self) -> None:
        """Test with zero seconds remaining."""
        error = AccountLockedError(seconds_remaining=0)

        assert "0 minutes" in error.detail


class TestInvalidTokenError:
    """Test cases for InvalidTokenError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = InvalidTokenError()

        assert error.detail == "Invalid or expired token"
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestInvalidRefreshTokenError:
    """Test cases for InvalidRefreshTokenError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = InvalidRefreshTokenError()

        assert error.detail == "Invalid refresh token"
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestTokenRevokedError:
    """Test cases for TokenRevokedError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = TokenRevokedError()

        assert error.detail == "Token has been revoked"
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestTokenExpiredError:
    """Test cases for TokenExpiredError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = TokenExpiredError()

        assert error.detail == "Token has expired"
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestUserDeactivatedError:
    """Test cases for UserDeactivatedError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = UserDeactivatedError()

        assert error.detail == "User account is deactivated"
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestEmailVerificationError:
    """Test cases for EmailVerificationError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = EmailVerificationError()

        assert "verification" in error.detail.lower()
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestPasswordResetError:
    """Test cases for PasswordResetError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = PasswordResetError()

        assert "reset" in error.detail.lower()
        assert error.status_code == HTTP_401_UNAUTHORIZED


class TestUserNotFoundError:
    """Test cases for UserNotFoundError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = UserNotFoundError()

        assert error.detail == "User not found"
        assert error.status_code == HTTP_404_NOT_FOUND


class TestUserNotVerifiedError:
    """Test cases for UserNotVerifiedError."""

    def test_default_message(self) -> None:
        """Test default error message."""
        error = UserNotVerifiedError()

        assert "verify" in error.detail.lower()
        assert error.status_code == HTTP_403_FORBIDDEN


class TestInsufficientPermissionsError:
    """Test cases for InsufficientPermissionsError."""

    def test_default_role(self) -> None:
        """Test default required role."""
        error = InsufficientPermissionsError()

        assert "admin" in error.detail
        assert error.status_code == HTTP_403_FORBIDDEN

    def test_custom_role(self) -> None:
        """Test custom required role."""
        error = InsufficientPermissionsError(required_role="moderator")

        assert "moderator" in error.detail
        assert error.status_code == HTTP_403_FORBIDDEN
