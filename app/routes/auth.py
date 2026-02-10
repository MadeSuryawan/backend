"""Authentication routes for handling user login, registration, and token management."""

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
from app.dependencies import AuthServiceDep, UserDBDep, UserRepoDep, UserRespDep, oauth2_scheme
from app.errors.auth import (
    EmailVerificationError,
    PasswordChangeError,
    PasswordResetError,
    VerificationTokenUsedError,
)
from app.managers.rate_limiter import limiter
from app.managers.token_manager import decode_access_token, decode_verification_token
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
        client_kwargs={"scope": "openid email profile"},
    )

if settings.WECHAT_APP_ID:
    oauth.register(
        name="wechat",
        client_id=settings.WECHAT_APP_ID,
        client_secret=settings.WECHAT_APP_SECRET,
        authorize_url="https://open.weixin.qq.com/connect/qrconnect",
        access_token_url="https://api.weixin.qq.com/sns/oauth2/access_token",
        client_kwargs={"scope": "snsapi_login"},
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
                "application/json": {"example": {"detail": "Invalid username or password"}},
            },
        },
        429: {
            "description": "Rate limit exceeded or account locked",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
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
    """Login with username (or email) and password."""
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
    """Exchange refresh token for new token pair."""
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
    """Logout and invalidate tokens."""
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
                    "example": {"detail": "Invalid or expired verification token"},
                },
            },
        },
        401: {
            "description": "Token already used",
            "content": {
                "application/json": {
                    "example": {"detail": "Verification token has already been used"},
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
    """Verify email with dedicated verification token."""
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
    Resend verification email.

    Always returns success to prevent email enumeration.
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
    """Request password reset email."""
    # Always return success to prevent email enumeration
    reset_token = await auth_service.send_password_reset(body.email)

    # In production, send email here with reset_token
    # For now, we just return success
    _ = reset_token  # Suppress unused warning

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
                "application/json": {"example": {"detail": "Invalid or expired reset token"}},
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
    """Reset password with token."""
    token_data = decode_access_token(body.token)
    if not token_data:
        raise PasswordResetError

    success = await auth_service.reset_password(token_data.user_id, body.new_password)
    if not success:
        raise PasswordResetError

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
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
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
                "application/json": {"example": {"detail": "Username or email already exists"}},
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
    """Register a new user."""
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
    description="Redirect user to the OAuth provider's login page.",
    responses={
        307: {"description": "Redirect to provider"},
        404: {
            "description": "Provider not configured",
            "content": {
                "application/json": {"example": {"detail": "Provider google not configured"}},
            },
        },
    },
    operation_id="auth_login_oauth",
)
@timed("/auth/login/oauth")
async def login_oauth(
    request: Request,
    response: Response,
    provider: str,
) -> RedirectResponse:
    """Initiate OAuth login flow."""
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Provider {provider} not configured",
        )

    redirect_uri = request.url_for("auth_callback", provider=provider)
    return await client.authorize_redirect(request, redirect_uri)


@router.get(
    "/callback/{provider}",
    name="auth_callback",
    include_in_schema=False,
    summary="OAuth callback",
    description="Handle the redirect from the OAuth provider.",
)
@timed("/auth/callback")
async def auth_callback(
    request: Request,
    response: Response,
    provider: str,
    auth_service: AuthServiceDep,
) -> Token:
    """Handle OAuth callback and exchange for local token."""
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Provider not found")

    try:
        token = await client.authorize_access_token(request)
        user_info = token.get("userinfo")
        if not user_info:
            user_info = await client.userinfo(token=token)

        user = await auth_service.get_or_create_oauth_user(dict(user_info), provider)
        return auth_service.create_token_for_user(user)
    except Exception as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=f"OAuth failed: {e!s}") from e


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
            "content": {"application/json": {"example": {"detail": "Not authenticated"}}},
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
    """Get current logged in user."""
    return UserResponse.model_validate(user_resp, from_attributes=True)
