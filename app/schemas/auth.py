"""Authentication schemas for JWT tokens and auth flows."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    """Token response schema with access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenOnly(BaseModel):
    """Token response schema with only access token (for legacy compatibility)."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token data schema for extracted token payload."""

    username: str
    user_id: UUID
    jti: str
    token_type: str


class TokenRefreshRequest(BaseModel):
    """Request schema for token refresh."""

    refresh_token: str = Field(..., description="The refresh token to exchange")


class LogoutRequest(BaseModel):
    """Request schema for logout."""

    refresh_token: str = Field(..., description="The refresh token to invalidate")


class EmailVerificationRequest(BaseModel):
    """Request schema for email verification."""

    token: str = Field(..., description="Email verification token")


class PasswordResetRequest(BaseModel):
    """Request schema for initiating password reset."""

    email: EmailStr = Field(..., description="Email address for password reset")


class PasswordResetConfirm(BaseModel):
    """Request schema for confirming password reset."""

    token: str = Field(..., description="Password reset token")
    new_password: str = Field(
        ...,
        min_length=8,
        description="New password (min 8 characters)",
    )


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
    success: bool = True


class VerificationTokenData(BaseModel):
    """
    Token data schema for email verification tokens.

    Attributes:
        user_id: User's UUID from token
        email: Email address the token was issued for (for validation)
        jti: JWT ID for token identification
    """

    user_id: UUID
    email: str
    jti: str | None = None


class ResendVerificationRequest(BaseModel):
    """Request schema for resending verification email."""

    email: EmailStr = Field(..., description="Email address to send verification to")
