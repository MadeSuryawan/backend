"""Authentication routes for handling user login and registration."""

from typing import Annotated

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import ORJSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from starlette.responses import RedirectResponse, Response
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from app.configs import settings
from app.decorators import timed
from app.dependencies import AuthServiceDep, UserRepoDep, UserRespDep
from app.managers import cache_manager, limiter
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserResponse
from app.utils.cache_keys import user_id_key, username_key, users_list_key

router = APIRouter(prefix="/auth", tags=["🔐 Auth"])

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
    # WeChat configuration (custom, as it might not follow strict OIDC)
    # Using a generic setup, might need adjustment for specialized WeChat flow
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
    description="Authenticate user with username/email and password to obtain an access token.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
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
            "description": "Rate limit exceeded",
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
    """
    Login with username (or email) and password.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    form_data : OAuth2PasswordRequestForm
        Form data containing username and password.
    auth_service : AuthService
        Authentication service dependency.

    Returns
    -------
    Token
        Access token object.

    Raises
    ------
    InvalidCredentialsError
        If authentication fails.
    """
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    return auth_service.create_token_for_user(user)


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
) -> UserResponse:
    """
    Register a new user.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_create : UserCreate
        User registration data.
    repo : UserRepository
        User repository dependency.

    Returns
    -------
    UserResponse
        Created user information.

    Raises
    ------
    HTTPException
        If registration fails (e.g. duplicate user).
    """
    try:
        user = await repo.create(user_create)
        # Clear cache so new user appears in lists immediately
        await cache_manager.delete(
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
        307: {
            "description": "Redirect to provider",
        },
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
    """
    Initiate OAuth login flow.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    provider : str
        OAuth provider name (e.g. 'google').

    Returns
    -------
    RedirectResponse
        Redirect to provider's consent page.

    Raises
    ------
    HTTPException
        If provider is not configured.
    """
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
    """
    Handle OAuth callback and exchange for local token.

    Parameters
    ----------
    request : Request
        Current request context containing auth code.
    response : Response
        Response object for middleware/decorators.
    provider : str
        OAuth provider name.
    auth_service : AuthService
        Authentication service dependency.

    Returns
    -------
    Token
        Access token object.

    Raises
    ------
    HTTPException
        If callback handling fails.
    """
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Provider not found")

    try:
        token = await client.authorize_access_token(request)
        user_info = token.get("userinfo")
        if not user_info:
            # Fallback for providers that don't return userinfo in token (like generic OAuth2)
            user_info = await client.userinfo(token=token)

        user = await auth_service.get_or_create_oauth_user(dict(user_info), provider)
        return auth_service.create_token_for_user(user)
    except Exception as e:
        # Log error in production
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
    """
    Get current logged in user.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_resp : UserResponse
        Authenticated user (resolved by dependency).

    Returns
    -------
    UserResponse
        Current user's profile information.
    """
    return UserResponse.model_validate(user_resp, from_attributes=True)
