"""
Authentication routes for user login, registration, and token management.

This module provides comprehensive authentication endpoints for the BaliBlissed
backend API, including:

- **Traditional Authentication**: Username/password login with JWT tokens
- **OAuth 2.0 Integration**: Google and WeChat OAuth providers
- **Email Verification**: Token-based email verification with rate limiting
- **Password Management**: Reset, change, and forgot password flows
- **Token Management**: Access token refresh and logout functionality

Security Features
-----------------
All endpoints implement multiple security layers:

- **Rate Limiting**: Prevents brute force and abuse attacks
- **CSRF Protection**: OAuth flows use cryptographically secure state parameters
- **Token Blacklisting**: Logout invalidates tokens server-side
- **Single-Use Tokens**: Verification and reset tokens can only be used once
- **Anti-Enumeration**: Password reset and verification endpoints return
  consistent responses to prevent user enumeration attacks
- **PKCE Support**: OAuth providers use Proof Key for Code Exchange

Dependencies
------------
- AuthService: Core authentication business logic
- UserRepository: Database operations for user entities
- CacheManager: Redis-backed caching for tokens and rate limits
- OAuth (authlib): OAuth 2.0 client for third-party providers

Notes
-----
All endpoints use ORJSONResponse for optimal JSON serialization performance.
Rate limits are enforced per-endpoint and can be configured via settings.
"""

import secrets
from logging import getLogger
from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import ORJSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from starlette.responses import RedirectResponse, Response
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_429_TOO_MANY_REQUESTS,
)

from app.configs import settings
from app.decorators.caching import get_cache_manager
from app.decorators.metrics import timed
from app.dependencies import (
    AuthServiceDep,
    CacheDep,
    UserDBDep,
    UserRepoDep,
    UserRespDep,
    oauth2_scheme,
)
from app.errors.auth import (
    EmailVerificationError,
    OAuthError,
    OAuthStateError,
    PasswordChangeError,
    PasswordResetError,
    ResetTokenUsedError,
    VerificationTokenUsedError,
)
from app.managers.rate_limiter import limiter
from app.managers.token_manager import (
    decode_password_reset_token,
    decode_verification_token,
)
from app.schemas.auth import (
    EmailVerificationRequest,
    LogoutRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    ResendVerificationRequest,
    Token,
    TokenRefreshRequest,
)
from app.schemas.user import UserCreate, UserResponse
from app.utils.cache_keys import user_id_key, username_key, users_list_key
from app.utils.helpers import file_logger

router = APIRouter(prefix="/auth", tags=["🔐 Auth"])
logger = file_logger(getLogger(__name__))

# OAuth Configuration
oauth = OAuth()

if settings.GOOGLE_CLIENT_ID:
    oauth.register(
        name="google",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",  # Enable PKCE
        },
    )

if settings.WECHAT_APP_ID:
    oauth.register(
        name="wechat",
        client_id=settings.WECHAT_APP_ID,
        client_secret=settings.WECHAT_APP_SECRET,
        authorize_url="https://open.weixin.qq.com/connect/qrconnect",
        access_token_url="https://api.weixin.qq.com/sns/oauth2/access_token",
        client_kwargs={
            "scope": "snsapi_login",
            "code_challenge_method": "S256",  # Enable PKCE
        },
    )


@router.post(
    "/login",
    response_class=ORJSONResponse,
    response_model=Token,
    summary="Login for access token",
    description="Authenticate with username/email and password to obtain tokens.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                    },
                },
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Oops! The email/username or password you entered doesn't match our records. Please try again.",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded or account locked",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Your account is temporarily locked for security reasons after multiple failed login attempts. Please try again later or reset your password.",
                    },
                },
            },
        },
    },
    operation_id="auth_login",
)
@timed("/auth/login")
@limiter.limit("5/minute")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    auth_service: AuthServiceDep,
) -> Token:
    r"""
    Authenticate user and issue JWT tokens.

    Authenticates a user using their username (or email) and password, then
    returns a fresh JWT token pair for subsequent API access.

    Security Features
    -----------------
    - **Rate Limited**: 5 requests per minute per IP to prevent brute force
    - **Account Lockout**: Accounts locked after 5 failed attempts
    - **Password Hashing**: Argon2 with configurable security levels
    - **Token Expiration**: Access tokens expire in 30 minutes (configurable)

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting by IP.
    response : Response
        The outgoing HTTP response.
    form_data : OAuth2PasswordRequestForm
        OAuth2 standard form containing:
        - ``username``: User's username or email address
        - ``password``: User's plaintext password
        - ``scope``: Optional space-separated scope list (unused)
        - ``grant_type``: Optional grant type (unused)
        - ``client_id``/``client_secret``: Optional client credentials (unused)
    auth_service : AuthService
        Authentication service for credential validation and token generation.

    Returns
    -------
    Token
        JWT token pair containing:
        - ``access_token``: Short-lived token for API authentication
        - ``refresh_token``: Long-lived token for token renewal
        - ``token_type``: Always "bearer"

    Raises
    ------
    UserAuthenticationError
        If credentials are invalid (401 Unauthorized).
    AccountLockedError
        If account is locked due to too many failed attempts (429 Too Many Requests).
    HTTPException
        If rate limit exceeded (429 Too Many Requests).

    Examples
    --------
    **Using curl:**

    .. code-block:: bash

        curl -X POST "https://api.example.com/auth/login" \
            -H "Content-Type: application/x-www-form-urlencoded" \
            -d "username=johndoe&password=secretpass123"

    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/login",
                data={"username": "johndoe", "password": "secretpass123"}
            )
            tokens = response.json()
            # {'access_token': 'eyJ...', 'refresh_token': 'eyJ...', 'token_type': 'bearer'}
    """
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    return auth_service.create_token_for_user(user)


@router.post(
    "/refresh",
    response_class=ORJSONResponse,
    response_model=Token,
    summary="Refresh access token",
    description="Exchange a refresh token for a new access and refresh token pair.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                    },
                },
            },
        },
        401: {
            "description": "Invalid or expired refresh token",
            "content": {"application/json": {"example": {"detail": "Invalid refresh token"}}},
        },
    },
    operation_id="auth_refresh",
)
@timed("/auth/refresh")
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    response: Response,
    body: TokenRefreshRequest,
    auth_service: AuthServiceDep,
) -> Token:
    """
    Exchange a refresh token for a new JWT token pair.

    Validates the provided refresh token and issues a new access/refresh
    token pair. The old refresh token is invalidated (one-time use).

    Security Features
    -----------------
    - **Rate Limited**: 10 requests per minute per IP
    - **One-Time Use**: Old refresh token is blacklisted after use
    - **Token Rotation**: Both tokens are rotated on each refresh
    - **Expiration Check**: Validates token hasn't expired (7 days default)

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    body : TokenRefreshRequest
        Request body containing:
        - ``refresh_token``: The refresh token obtained from login or previous refresh
    auth_service : AuthService
        Authentication service for token validation and generation.

    Returns
    -------
    Token
        New JWT token pair with fresh access and refresh tokens.

    Raises
    ------
    InvalidTokenError
        If the refresh token is invalid, expired, or already used (401 Unauthorized).
    HTTPException
        If rate limit exceeded (429 Too Many Requests).

    Notes
    -----
    Clients should store the new refresh token after each refresh operation.
    The old refresh token becomes invalid immediately after this call.

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/refresh",
                json={"refresh_token": old_refresh_token}
            )
            new_tokens = response.json()
    """
    return await auth_service.refresh_tokens(body.refresh_token)


@router.post(
    "/logout",
    response_class=ORJSONResponse,
    response_model=MessageResponse,
    summary="Logout user",
    description="Invalidate current access and refresh tokens.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"message": "Successfully logged out", "success": True},
                },
            },
        },
    },
    operation_id="auth_logout",
)
@timed("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    token: Annotated[str, Depends(oauth2_scheme)],
    body: LogoutRequest,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    """
    Logout user and invalidate all tokens.

    Blacklists the current access token and associated refresh token,
    preventing further API access with those credentials. The user will
    need to re-authenticate to obtain new tokens.

    Security Features
    -----------------
    - **Token Blacklisting**: Both access and refresh tokens are blacklisted
    - **Redis Storage**: Blacklisted tokens stored in Redis with TTL matching expiration
    - **Immediate Invalidation**: Tokens become invalid immediately after logout
    - **Multi-Device Logout**: Optionally invalidate all user's refresh tokens

    Parameters
    ----------
    request : Request
        The incoming HTTP request.
    response : Response
        The outgoing HTTP response.
    token : str
        The current access token (extracted from Authorization header via OAuth2Scheme).
    body : LogoutRequest
        Request body containing:
        - ``refresh_token``: The refresh token to invalidate
        - ``logout_all``: If true, invalidates all user's refresh tokens (optional)
    auth_service : AuthService
        Authentication service for token blacklisting.

    Returns
    -------
    MessageResponse
        Success confirmation with message and status.

    Raises
    ------
    InvalidTokenError
        If the access token is invalid or already blacklisted (401 Unauthorized).

    Notes
    -----
    - Access tokens remain in Redis blacklist until their natural expiration
    - After logout, any API calls with the old tokens will return 401 Unauthorized
    - For security, always call logout when user explicitly signs out

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"refresh_token": refresh_token}
            )
            # {'message': 'Successfully logged out', 'success': True}
    """
    await auth_service.logout_user(token, body.refresh_token)
    return MessageResponse(message="Successfully logged out", success=True)


@router.post(
    "/verify-email",
    response_class=ORJSONResponse,
    response_model=MessageResponse,
    summary="Verify email address",
    description="Verify user email with the token sent to their email.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"message": "Email verified successfully", "success": True},
                },
            },
        },
        400: {
            "description": "Invalid token",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This verification link is invalid or has expired. Please request a new verification email to try again.",
                    },
                },
            },
        },
        401: {
            "description": "Token already used",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This verification link has already been used. Your email may already be verified - try signing in.",
                    },
                },
            },
        },
    },
    operation_id="auth_verify_email",
)
@timed("/auth/verify-email")
@limiter.limit("10/hour")
async def verify_email(
    request: Request,
    response: Response,
    body: EmailVerificationRequest,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    """
    Verify user's email address using a verification token.

    Validates the email verification token sent to the user's email address
    and marks the account as verified. Verification tokens are single-use
    and expire after a configurable period.

    Security Features
    -----------------
    - **Rate Limited**: 10 requests per hour per IP
    - **Single-Use Tokens**: Token JTI is tracked to prevent reuse
    - **Token Binding**: Token includes email claim for additional validation
    - **Expiration**: Tokens expire after VERIFICATION_TOKEN_EXPIRE_HOURS (default 24h)
    - **Redis Tracking**: Used tokens stored in Redis until natural expiration

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    body : EmailVerificationRequest
        Request body containing:
        - ``token``: The JWT verification token from email link
    auth_service : AuthService
        Authentication service for email verification operations.

    Returns
    -------
    MessageResponse
        Success confirmation with message and status.

    Raises
    ------
    EmailVerificationError
        If the token is invalid, expired, or email doesn't match (400 Bad Request).
    VerificationTokenUsedError
        If the token has already been used (401 Unauthorized).
    HTTPException
        If rate limit exceeded (429 Too Many Requests).

    Notes
    -----
    - After verification, user.is_verified is set to True
    - Verified users gain access to features requiring email verification
    - Token is decoded with dedicated verification secret (separate from auth)

    Examples
    --------
    **Verification flow:**

    1. User receives email with link: ``https://app.com/verify?token=eyJ...``
    2. Frontend extracts token and calls this endpoint:

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/verify-email",
                json={"token": verification_token_from_email}
            )
            # {'message': 'Email verified successfully', 'success': True}
    """
    # Use dedicated verification token decoder
    token_data = decode_verification_token(body.token)
    if not token_data:
        raise EmailVerificationError

    # Security: Check if token has already been used
    if token_data.jti and await auth_service.is_verification_token_used(token_data.jti):
        raise VerificationTokenUsedError

    # Verify email - passes full token_data for email claim validation
    success = await auth_service.verify_email(token_data)
    if not success:
        raise EmailVerificationError

    # Security: Mark token as used to prevent reuse
    if token_data.jti:
        await auth_service.mark_verification_token_used(
            token_data.jti,
            expires_hours=settings.VERIFICATION_TOKEN_EXPIRE_HOURS,
        )

    return MessageResponse(message="Email verified successfully", success=True)


@router.post(
    "/resend-verification",
    response_class=ORJSONResponse,
    response_model=MessageResponse,
    summary="Resend verification email",
    description="Resend the verification email to the user.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "message": "If your email is registered and unverified, a new verification email has been sent",
                        "success": True,
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {"example": {"detail": "Too Many Requests"}},
            },
        },
    },
    operation_id="auth_resend_verification",
)
@timed("/auth/resend-verification")
@limiter.limit("3/hour")
async def resend_verification(
    request: Request,
    response: Response,
    body: ResendVerificationRequest,
    auth_service: AuthServiceDep,
    repo: UserRepoDep,
) -> MessageResponse:
    """
    Resend email verification link to user.

    Sends a new verification email if the provided email exists and the
    associated account is not yet verified. Always returns success to
    prevent email enumeration attacks.

    Security Features
    -----------------
    - **Rate Limited**: 3 requests per hour per IP
    - **Anti-Enumeration**: Always returns success regardless of email existence
    - **Per-User Rate Limit**: Additional rate limit per user UUID
    - **Silent Failure**: No error if email doesn't exist or already verified

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    body : ResendVerificationRequest
        Request body containing:
        - ``email``: The email address to send verification to
    auth_service : AuthService
        Authentication service for sending verification emails.
    repo : UserRepository
        Repository for user lookup operations.

    Returns
    -------
    MessageResponse
        Generic success message (same response whether email exists or not).

    Raises
    ------
    HTTPException
        If rate limit exceeded for this specific user (429 Too Many Requests).

    Notes
    -----
    - Response is intentionally identical for existing/non-existing emails
    - Email is only sent if user exists AND is not yet verified
    - Per-user rate limiting prevents spamming a single account
    - New token invalidates any previous unused tokens

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/resend-verification",
                json={"email": "user@example.com"}
            )
            # {'message': 'If your email is registered...', 'success': True}
    """
    # Look up user by email (always return success regardless)
    user = await repo.get_by_email(body.email)

    if user and not user.is_verified:
        # Check rate limit
        can_send = await auth_service.check_verification_rate_limit(user.uuid)
        if not can_send:
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification email requests. Please try again later.",
            )

        # Generate and send verification token
        await auth_service.send_verification_email(user)
        await auth_service.record_verification_sent(user.uuid)

    # Always return success to prevent email enumeration
    return MessageResponse(
        message="If your email is registered and unverified, a new verification email has been sent",
        success=True,
    )


@router.post(
    "/forgot-password",
    response_class=ORJSONResponse,
    response_model=MessageResponse,
    summary="Request password reset",
    description="Send a password reset email to the user.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "message": "If the email exists, a reset link has been sent",
                        "success": True,
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {"example": {"detail": "Too Many Requests"}},
            },
        },
    },
    operation_id="auth_forgot_password",
)
@timed("/auth/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(
    request: Request,
    response: Response,
    body: PasswordResetRequest,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    """
    Initiate password reset flow by sending reset email.

    Generates a password reset token and sends it to the user's email
    if the account exists. Always returns success to prevent email
    enumeration attacks.

    Security Features
    -----------------
    - **Rate Limited**: 3 requests per hour per IP
    - **Anti-Enumeration**: Always returns success regardless of email existence
    - **Internal Rate Limiting**: Service prevents spam to same email
    - **Token Binding**: Reset token bound to user ID and email
    - **Short Expiration**: Tokens expire after PASSWORD_RESET_TOKEN_EXPIRE_HOURS

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    body : PasswordResetRequest
        Request body containing:
        - ``email``: The email address for the account to reset
    auth_service : AuthService
        Authentication service for password reset operations.

    Returns
    -------
    MessageResponse
        Generic success message (same response whether email exists or not).

    Notes
    -----
    - Response is intentionally identical for existing/non-existing emails
    - Email is only sent if user exists with that email
    - Token includes user ID and email for validation during reset
    - Previous unused tokens are not invalidated (check during reset)

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/forgot-password",
                json={"email": "user@example.com"}
            )
            # {'message': 'If the email exists, a reset link has been sent', 'success': True}
    """
    # Always return success to prevent email enumeration
    # The service handles rate limiting internally
    await auth_service.send_password_reset(body.email)

    return MessageResponse(
        message="If the email exists, a reset link has been sent",
        success=True,
    )


@router.post(
    "/reset-password",
    response_class=ORJSONResponse,
    response_model=MessageResponse,
    summary="Reset password",
    description="Reset password using the token from the reset email.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"message": "Password reset successfully", "success": True},
                },
            },
        },
        400: {
            "description": "Invalid token",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This password reset link is invalid or has expired. Please request a new password reset email.",
                    },
                },
            },
        },
        401: {
            "description": "Token already used",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This password reset link has already been used. Please request a new one if you still need to reset your password.",
                    },
                },
            },
        },
    },
    operation_id="auth_reset_password",
)
@timed("/auth/reset-password")
@limiter.limit("5/hour")
async def reset_password(
    request: Request,
    response: Response,
    body: PasswordResetConfirm,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    """
    Reset user password using token from reset email.

    Validates the password reset token and updates the user's password.
    The token is single-use and becomes invalid after successful reset.

    Security Features
    -----------------
    - **Rate Limited**: 5 requests per hour per IP
    - **Single-Use Tokens**: Token JTI tracked to prevent reuse
    - **Email Binding**: Validates email hasn't changed since token was issued
    - **Token Expiration**: Tokens expire after PASSWORD_RESET_TOKEN_EXPIRE_HOURS
    - **Password Hashing**: New password hashed with Argon2
    - **Confirmation Email**: User notified of password change via email

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    body : PasswordResetConfirm
        Request body containing:
        - ``token``: The JWT reset token from email link
        - ``new_password``: The new password to set
        - ``confirm_new_password``: Confirmation of new password (must match)
    auth_service : AuthService
        Authentication service for password reset operations.

    Returns
    -------
    MessageResponse
        Success confirmation with message and status.

    Raises
    ------
    PasswordResetError
        If token is invalid, expired, or email doesn't match (400 Bad Request).
    ResetTokenUsedError
        If the token has already been used (401 Unauthorized).
    HTTPException
        If rate limit exceeded (429 Too Many Requests).

    Notes
    -----
    - Token is decoded with dedicated password reset secret
    - Email validation prevents token reuse after email change
    - All existing refresh tokens remain valid (consider logout_all)
    - User receives confirmation email after successful reset

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/reset-password",
                json={
                    "token": reset_token_from_email,
                    "new_password": "NewSecurePass123!",
                    "confirm_new_password": "NewSecurePass123!"
                }
            )
            # {'message': 'Password reset successfully', 'success': True}
    """
    # Use dedicated password reset token decoder
    token_data = decode_password_reset_token(body.token)
    if not token_data:
        raise PasswordResetError

    # Security: Check if token has already been used
    if token_data.jti and await auth_service.is_reset_token_used(token_data.jti):
        raise ResetTokenUsedError

    # Get user and validate email hasn't changed since token was issued
    user = await auth_service.user_repo.get_by_id(token_data.user_id)
    if not user or user.email != token_data.email:
        raise PasswordResetError

    # Reset the password
    success = await auth_service.reset_password(token_data.user_id, body.new_password)
    if not success:
        raise PasswordResetError

    # Security: Mark token as used to prevent reuse
    if token_data.jti:
        await auth_service.mark_reset_token_used(
            token_data.jti,
            expires_hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
        )

    return MessageResponse(message="Password reset successfully", success=True)


@router.post(
    "/change-password",
    response_class=ORJSONResponse,
    response_model=MessageResponse,
    status_code=HTTP_200_OK,
    summary="Change password",
    description="Change password for logged-in user. Requires current password verification.",
    responses={
        200: {
            "description": "Password changed successfully",
            "content": {
                "application/json": {
                    "example": {"message": "Password changed successfully", "success": True},
                },
            },
        },
        400: {
            "description": "Invalid old password or validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Failed to change password. Please verify your current password.",
                    },
                },
            },
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Your session has expired or is no longer valid. Please sign in again to continue.",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="auth_change_password",
)
@timed("/auth/change-password")
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    response: Response,
    body: PasswordChangeRequest,
    current_user: UserDBDep,
    auth_service: AuthServiceDep,
) -> MessageResponse:
    """
    Change password for authenticated user.

    Verifies the current password before updating to the new password.
    All existing refresh tokens are invalidated, forcing re-login on other devices.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.
    response : Response
        The outgoing HTTP response.
    body : PasswordChangeRequest
        Contains old_password, new_password, and confirm_new_password.
    current_user : UserDB
        The currently authenticated user from JWT token.
    auth_service : AuthService
        The authentication service for password operations.

    Returns
    -------
    MessageResponse
        Success message if password changed successfully.

    Raises
    ------
    PasswordChangeError
        If old password is incorrect or user not found.
    """
    success = await auth_service.change_password(
        user_id=current_user.uuid,
        old_password=body.old_password,
        new_password=body.new_password,
    )
    if not success:
        raise PasswordChangeError

    return MessageResponse(message="Password changed successfully", success=True)


@router.post(
    "/register",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    status_code=HTTP_201_CREATED,
    summary="Register a new user",
    description="Register a new user account with the provided information.",
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "firstName": "John",
                        "lastName": "Doe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                        "createdAt": "2025-01-01",
                        "updatedAt": "2025-01-01",
                        "country": "N/A",
                        "displayName": "John Doe",
                    },
                },
            },
        },
        400: {
            "description": "Bad Request",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "An account with this username or email already exists. Please sign in instead or use a different email.",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="auth_register",
)
@timed("/auth/register")
@limiter.limit("5/hour")
async def register_user(
    request: Request,
    response: Response,
    user_create: UserCreate,
    repo: UserRepoDep,
    auth_service: AuthServiceDep,
) -> UserResponse:
    """
    Register a new user account.

    Creates a new user account with the provided information and sends
    a verification email to confirm the email address. The user is
    created as inactive until email verification is complete.

    Security Features
    -----------------
    - **Rate Limited**: 5 requests per hour per IP
    - **Password Hashing**: Password hashed with Argon2 before storage
    - **Email Verification**: Verification email sent automatically
    - **Unique Constraints**: Username and email must be unique
    - **Input Validation**: All fields validated via Pydantic schemas

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    user_create : UserCreate
        Registration data containing:
        - ``username``: Unique username (alphanumeric, underscores)
        - ``email``: Valid email address
        - ``password``: Password meeting complexity requirements
        - ``first_name``: User's first name (optional)
        - ``last_name``: User's last name (optional)
        - ``country``: User's country (optional)
    repo : UserRepository
        Repository for user creation operations.
    auth_service : AuthService
        Authentication service for sending verification email.

    Returns
    -------
    UserResponse
        Created user data (without sensitive information).

    Raises
    ------
    HTTPException
        If username or email already exists (400 Bad Request).
    HTTPException
        If rate limit exceeded (429 Too Many Requests).

    Notes
    -----
    - User is created with is_verified=False and is_active=True
    - Verification email is sent asynchronously
    - User cache is invalidated after creation
    - Password is hashed before database storage

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.example.com/auth/register",
                json={
                    "username": "johndoe",
                    "email": "john@example.com",
                    "password": "SecurePass123!",
                    "first_name": "John",
                    "last_name": "Doe"
                }
            )
            user = response.json()
            # {'id': 'uuid...', 'username': 'johndoe', 'email': 'john@example.com', ...}
    """
    try:
        user = await repo.create(user_create)

        # Trigger verification email
        await auth_service.send_verification_email(user)
        await auth_service.record_verification_sent(user.uuid)

        await get_cache_manager(request).delete(
            user_id_key(user.uuid),
            username_key(user.username),
            users_list_key(0, 10),
            namespace="users",
        )
        return UserResponse.model_validate(user, from_attributes=True)
    except Exception as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get(
    "/login/{provider}",
    summary="Initiate OAuth login",
    description="""Redirect user to the OAuth provider's login page with CSRF protection.

    **Security Features:**
    - Generates a cryptographically secure `state` parameter to prevent CSRF attacks
    - Stores state in cache with 10-minute TTL
    - Enables PKCE (Proof Key for Code Exchange) for enhanced security
    - Rate limited to prevent abuse

    **Supported Providers:**
    - `google` - Google OAuth 2.0 (requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    - `wechat` - WeChat Open Platform (requires WECHAT_APP_ID and WECHAT_APP_SECRET)

    **Flow:**
    1. Call this endpoint to get a redirect to the OAuth provider
    2. User authenticates with the provider
    3. Provider redirects to `/auth/callback/{provider}` with authorization code
    4. Exchange code for JWT tokens

    **Note:** The callback URL must be registered in your OAuth provider settings.
    """,
    responses={
        307: {
            "description": "Temporary redirect to OAuth provider authorization page",
            "headers": {
                "Location": {
                    "description": "OAuth provider authorization URL with state parameter",
                    "schema": {"type": "string"},
                },
                "Set-Cookie": {
                    "description": "Session cookie for OAuth state management",
                    "schema": {"type": "string"},
                },
            },
        },
        404: {
            "description": "Provider not configured",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This sign-in method is not available right now. Please try a different sign-in option.",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {"example": {"detail": "Too Many Requests"}},
            },
        },
    },
    operation_id="auth_login_oauth",
    tags=["🔐 OAuth"],
)
@timed("/auth/login/oauth")
@limiter.limit("10/minute")
async def login_oauth(
    request: Request,
    response: Response,
    provider: str,
    cache: CacheDep,
) -> RedirectResponse:
    """
    Initiate OAuth login flow with CSRF protection.

    Generates a cryptographically secure state parameter to prevent CSRF attacks.
    The state is stored in cache with a TTL and validated in the callback.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.
    response : Response
        The outgoing HTTP response.
    provider : str
        The OAuth provider name (e.g., 'google', 'wechat').
    cache : CacheDep
        Cache manager for storing the state parameter.

    Returns
    -------
    RedirectResponse
        Redirects to the OAuth provider's authorization endpoint.

    Raises
    ------
    HTTPException
        If the provider is not configured.
    """
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="This sign-in method is not available right now. Please try a different sign-in option.",
        )

    # Generate cryptographically secure state parameter for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state in cache with TTL (single-use, expires after callback or timeout)
    state_key = f"oauth_state:{state}"
    await cache.set(
        state_key,
        {"provider": provider, "ip": request.client.host if request.client else None},
        ttl=settings.OAUTH_STATE_EXPIRE_SECONDS,
    )

    redirect_uri = request.url_for("auth_callback", provider=provider)
    return await client.authorize_redirect(request, redirect_uri, state=state)


@router.get(
    "/callback/{provider}",
    name="auth_callback",
    response_class=ORJSONResponse,
    response_model=Token,
    summary="OAuth callback handler",
    description="""Handle the redirect from the OAuth provider and exchange for local JWT tokens.

    **Security Validation:**
    - Validates the `state` parameter to prevent CSRF attacks
    - Ensures state is single-use (deleted after validation)
    - Verifies provider matches the state stored during login
    - State expires after 10 minutes
    - Rate limited to prevent abuse

    **Flow:**
    1. Receives authorization `code` and `state` from OAuth provider
    2. Validates state exists in cache and matches provider
    3. Exchanges code for access token with provider
    4. Fetches user info from provider
    5. Creates or retrieves local user
    6. Returns JWT access and refresh tokens

    **Note:** This endpoint is called by OAuth providers, not directly by clients.
    """,
    responses={
        200: {
            "description": "Successfully authenticated, JWT tokens returned",
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                        "token_type": "bearer",
                    },
                },
            },
        },
        400: {
            "description": "Invalid request - missing/invalid state or OAuth error",
            "content": {
                "application/json": {
                    "examples": {
                        "missing_state": {
                            "value": {
                                "detail": "For your security, this sign-in attempt couldn't be verified. Please try signing in again.",
                            },
                        },
                        "invalid_state": {
                            "value": {
                                "detail": "For your security, this sign-in session has expired. Please try signing in again.",
                            },
                        },
                        "provider_mismatch": {
                            "value": {
                                "detail": "There was a problem with your sign-in. Please try again or use a different sign-in method.",
                            },
                        },
                        "oauth_failed": {
                            "value": {
                                "detail": "We couldn't complete your sign-in with this provider. Please try again or use a different sign-in method.",
                            },
                        },
                    },
                },
            },
        },
        404: {
            "description": "Provider not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "This sign-in method is not available right now. Please try a different sign-in option.",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="auth_oauth_callback",
    tags=["🔐 OAuth"],
    include_in_schema=True,
)
@timed("/auth/callback")
@limiter.limit("20/minute")
async def auth_callback(
    request: Request,
    response: Response,
    provider: str,
    auth_service: AuthServiceDep,
    cache: CacheDep,
) -> Token:
    """
    Handle OAuth callback and exchange for local token.

    Validates the state parameter to prevent CSRF attacks. The state must exist
    in cache and match the provider. It is deleted after validation (single-use).

    Parameters
    ----------
    request : Request
        The incoming HTTP request containing the authorization code and state.
    response : Response
        The outgoing HTTP response.
    provider : str
        The OAuth provider name (e.g., 'google', 'wechat').
    auth_service : AuthServiceDep
        Authentication service for user management.
    cache : CacheDep
        Cache manager for validating and deleting the state parameter.

    Returns
    -------
    Token
        JWT access and refresh tokens for the authenticated user.

    Raises
    ------
    OAuthStateError
        If the state parameter is missing, invalid, or expired.
    OAuthError
        If the OAuth provider returns an error or token exchange fails.
    HTTPException
        If the provider is not found or other unexpected errors occur.
    """
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="This sign-in method is not available right now. Please try a different sign-in option.",
        )

    # Validate state parameter for CSRF protection
    state = request.query_params.get("state")
    if not state:
        logger.warning("OAuth callback missing state parameter", extra={"provider": provider})
        raise OAuthStateError("Missing OAuth state parameter")  # noqa: TRY003

    state_key = f"oauth_state:{state}"
    cached_value = await cache.get(state_key)

    if not isinstance(cached_value, dict):
        logger.warning(
            "OAuth state validation failed: state not found or expired",
            extra={"provider": provider, "state": state[:8] + "..."},
        )
        raise OAuthStateError("Invalid or expired OAuth state")  # noqa: TRY003

    stored_state: dict[str, str | None] = cached_value

    if stored_state.get("provider") != provider:
        logger.warning(
            "OAuth state validation failed: provider mismatch",
            extra={"expected": stored_state.get("provider"), "got": provider},
        )
        raise OAuthStateError("OAuth provider mismatch")  # noqa: TRY003

    # Delete state immediately after validation (single-use token)
    await cache.delete(state_key)

    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:  # authlib raises various exceptions for OAuth errors
        error_desc = getattr(exc, "description", str(exc))
        logger.warning(
            "OAuth token exchange failed",
            extra={"provider": provider, "error": error_desc},
        )
        msg = f"OAuth authorization failed: {error_desc}"
        raise OAuthError(msg) from exc

    try:
        user_info = token.get("userinfo")
        if not user_info:
            user_info = await client.userinfo(token=token)

        user = await auth_service.get_or_create_oauth_user(dict(user_info), provider)
        return auth_service.create_token_for_user(user)
    except OAuthError:
        # Re-raise OAuthError as-is
        raise
    except Exception as exc:
        logger.exception("OAuth user processing failed", extra={"provider": provider})
        msg = f"OAuth user processing failed: {exc!s}"
        raise OAuthError(msg) from exc


@router.get(
    "/me",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Get current user",
    description="Retrieve the profile of the currently authenticated user.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": True,
                    },
                },
            },
        },
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Your session has expired or is no longer valid. Please sign in again to continue.",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="auth_me",
)
@timed("/auth/me")
@limiter.limit("50/minute")
async def read_users_me(
    request: Request,
    response: Response,
    user_resp: UserRespDep,
) -> UserResponse:
    """
    Retrieve the currently authenticated user's profile.

    Returns the profile information of the user associated with the
    current access token. This endpoint is commonly used to verify
    authentication status and fetch user details for UI display.

    Security Features
    -----------------
    - **Rate Limited**: 50 requests per minute per IP
    - **Authentication Required**: Valid access token in Authorization header
    - **Token Validation**: Token signature and expiration verified
    - **No Sensitive Data**: Password hash excluded from response

    Parameters
    ----------
    request : Request
        The incoming HTTP request, used for rate limiting.
    response : Response
        The outgoing HTTP response.
    user_resp : UserResponse
        The authenticated user (injected via dependency from JWT token).

    Returns
    -------
    UserResponse
        Current user's profile data including:
        - ``id``: User's UUID
        - ``username``: Username
        - ``email``: Email address
        - ``first_name``: First name (if set)
        - ``last_name``: Last name (if set)
        - ``is_active``: Account active status
        - ``is_verified``: Email verification status
        - ``role``: User role (user/admin)
        - ``created_at``: Account creation timestamp
        - ``updated_at``: Last update timestamp

    Raises
    ------
    HTTPException
        If not authenticated (401 Unauthorized).
    HTTPException
        If rate limit exceeded (429 Too Many Requests).

    Notes
    -----
    - User is extracted from JWT token via dependency injection
    - Response is cached at the client level (not server-side)
    - Use this endpoint to verify token validity after refresh

    Examples
    --------
    **Using Python httpx:**

    .. code-block:: python

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.example.com/auth/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user = response.json()
            # {'id': 'uuid...', 'username': 'johndoe', 'email': 'john@example.com', ...}
    """
    return UserResponse.model_validate(user_resp, from_attributes=True)
