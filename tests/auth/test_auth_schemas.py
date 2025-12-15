"""Tests for authentication schemas."""

from uuid import uuid4

from pydantic import ValidationError
from pytest import raises

from app.schemas.auth import (
    EmailVerificationRequest,
    LogoutRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    TokenData,
    TokenRefreshRequest,
)


class TestTokenSchema:
    """Test cases for Token schema."""

    def test_valid_token(self) -> None:
        """Test creating a valid token."""
        token = Token(
            access_token="access.token.here",
            refresh_token="refresh.token.here",
            token_type="bearer",
        )

        assert token.access_token == "access.token.here"
        assert token.refresh_token == "refresh.token.here"
        assert token.token_type == "bearer"

    def test_default_token_type(self) -> None:
        """Test that token_type defaults to 'bearer'."""
        token = Token(
            access_token="access.token.here",
            refresh_token="refresh.token.here",
        )

        assert token.token_type == "bearer"


class TestTokenDataSchema:
    """Test cases for TokenData schema."""

    def test_valid_token_data(self) -> None:
        """Test creating valid token data."""
        user_id = uuid4()
        token_data = TokenData(
            username="testuser",
            user_id=user_id,
            jti="jti-123",
            token_type="access",
        )

        assert token_data.username == "testuser"
        assert token_data.user_id == user_id
        assert token_data.jti == "jti-123"
        assert token_data.token_type == "access"


class TestTokenRefreshRequestSchema:
    """Test cases for TokenRefreshRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid refresh request."""
        request = TokenRefreshRequest(refresh_token="refresh.token.here")

        assert request.refresh_token == "refresh.token.here"

    def test_missing_token_raises_error(self) -> None:
        """Test that missing token raises validation error."""
        with raises(ValidationError):
            TokenRefreshRequest()  # type: ignore[call-arg]


class TestLogoutRequestSchema:
    """Test cases for LogoutRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid logout request."""
        request = LogoutRequest(refresh_token="refresh.token.here")

        assert request.refresh_token == "refresh.token.here"


class TestEmailVerificationRequestSchema:
    """Test cases for EmailVerificationRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid email verification request."""
        request = EmailVerificationRequest(token="verification.token.here")

        assert request.token == "verification.token.here"


class TestPasswordResetRequestSchema:
    """Test cases for PasswordResetRequest schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid password reset request."""
        request = PasswordResetRequest(email="test@example.com")

        assert request.email == "test@example.com"

    def test_invalid_email_raises_error(self) -> None:
        """Test that invalid email raises validation error."""
        with raises(ValidationError):
            PasswordResetRequest(email="not-an-email")


class TestPasswordResetConfirmSchema:
    """Test cases for PasswordResetConfirm schema."""

    def test_valid_request(self) -> None:
        """Test creating a valid password reset confirm request."""
        request = PasswordResetConfirm(
            token="reset.token.here",
            new_password="newpassword123",
        )

        assert request.token == "reset.token.here"
        assert request.new_password == "newpassword123"

    def test_short_password_raises_error(self) -> None:
        """Test that password shorter than 8 chars raises error."""
        with raises(ValidationError):
            PasswordResetConfirm(
                token="reset.token.here",
                new_password="short",  # Too short
            )


class TestMessageResponseSchema:
    """Test cases for MessageResponse schema."""

    def test_valid_response(self) -> None:
        """Test creating a valid message response."""
        response = MessageResponse(message="Success", success=True)

        assert response.message == "Success"
        assert response.success is True

    def test_default_success(self) -> None:
        """Test that success defaults to True."""
        response = MessageResponse(message="Success")

        assert response.success is True
