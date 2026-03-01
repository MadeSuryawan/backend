"""
OAuth authentication routes for third-party provider integration.

This module provides OAuth 2.0 authentication endpoints for the BaliBlissed
backend API, including:

- **Google OAuth 2.0**: OpenID Connect integration with PKCE
- **WeChat Open Platform**: QR code login integration

Security Features
-----------------
All OAuth endpoints implement multiple security layers:

- **CSRF Protection**: Cryptographically secure state parameters
- **PKCE Support**: Proof Key for Code Exchange for enhanced security
- **State Validation**: Single-use state tokens with TTL
- **Rate Limiting**: Prevents abuse of OAuth endpoints

Dependencies
------------
- AuthService: Core authentication business logic
- CacheManager: Redis-backed caching for state parameters
- OAuth (authlib): OAuth 2.0 client for third-party providers

Notes
-----
All endpoints use ORJSONResponse for optimal JSON serialization performance.
State parameters are stored in Redis with configurable TTL.
"""

from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Annotated

from authlib.integrations.starlette_client import StarletteOAuth2App as OAuthClient
from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse
from starlette.responses import RedirectResponse, Response

from app.configs.settings import settings
from app.decorators.metrics import timed
from app.dependencies import AuthServiceDep, CacheDep, OauthDep
from app.errors.auth import OAuthError, OAuthStateError
from app.logging import get_logger
from app.managers.rate_limiter import limiter
from app.schemas.auth import Token
from app.services.auth import AuthService
from app.services.geo_timezone import detect_timezone_by_ip

router = APIRouter(prefix="/auth", tags=["🔐 OAuth"])
logger = get_logger(__name__)


async def _validate_oauth_state(
    provider: str,
    state: str | None,
    cache: CacheDep,
) -> dict[str, str | None]:
    """
    Validate OAuth state parameter for CSRF protection.

    Parameters
    ----------
    provider : str
        The expected OAuth provider name.
    state : str | None
        The state parameter from the callback request.
    cache : CacheDep
        Cache manager for state validation.

    Returns
    -------
    dict[str, str | None]
        The stored state data containing provider and IP.

    Raises
    ------
    OAuthStateError
        If state is missing, invalid, expired, or provider mismatch.
    """
    if not state:
        logger.warning("OAuth callback missing state parameter", extra={"provider": provider})
        details = "Missing OAuth state parameter"
        raise OAuthStateError(details)

    state_key = f"oauth_state:{state}"
    cached_value = await cache.get(state_key)

    if not isinstance(cached_value, dict):
        logger.warning(
            "OAuth state validation failed: state not found or expired",
            extra={"provider": provider, "state": state[:8] + "..."},
        )
        details = "Invalid or expired OAuth state"
        raise OAuthStateError(details)

    stored_state: dict[str, str | None] = cached_value

    if stored_state.get("provider") != provider:
        logger.warning(
            "OAuth state validation failed: provider mismatch",
            extra={"expected": stored_state.get("provider"), "got": provider},
        )
        details = "OAuth provider mismatch"
        raise OAuthStateError(details)

    # Delete state immediately after validation (single-use token)
    await cache.delete(state_key)

    return stored_state


async def _detect_user_timezone(request: Request) -> str:
    """
    Detect user timezone from request headers or IP geolocation.

    Parameters
    ----------
    request : Request
        The incoming HTTP request.

    Returns
    -------
    str
        The detected timezone string (defaults to 'UTC').
    """
    user_timezone = getattr(request.state, "user_timezone", "UTC")

    if user_timezone == "UTC":
        client_ip = request.client.host if request.client else None
        if client_ip:
            user_timezone = await detect_timezone_by_ip(client_ip)

    return user_timezone


async def _exchange_oauth_token(
    client: OAuthClient,
    request: Request,
    provider: str,
) -> dict:
    """
    Exchange authorization code for OAuth access token.

    Parameters
    ----------
    client : OAuthClient
        The OAuth client for the provider.
    request : Request
        The incoming HTTP request with authorization code.
    provider : str
        The OAuth provider name for logging.

    Returns
    -------
    dict
        The token response from the OAuth provider.

    Raises
    ------
    OAuthError
        If token exchange fails.
    """
    try:
        return await client.authorize_access_token(request)
    except Exception as exc:
        error_desc = getattr(exc, "description", str(exc))
        logger.warning(
            "OAuth token exchange failed",
            extra={"provider": provider, "error": error_desc},
        )
        details = f"OAuth authorization failed: {error_desc}"
        raise OAuthError(details) from exc


async def _get_user_info(
    client: OAuthClient,
    token: dict,
) -> dict:
    """
    Extract user info from token or fetch from provider.

    Parameters
    ----------
    client : OAuthClient
        The OAuth client for the provider.
    token : dict
        The token response from the OAuth provider.

    Returns
    -------
    dict
        User information from the OAuth provider.
    """
    user_info = token.get("userinfo")
    if not user_info:
        user_info = await client.userinfo(token=token)
    return dict(user_info)


async def _process_oauth_user(
    client: OAuthClient,
    token: dict,
    provider: str,
    request: Request,
    auth_service: AuthService,
) -> Token:
    """
    Process OAuth user and return JWT tokens.

    Parameters
    ----------
    client : OAuthClient
        The OAuth client for the provider.
    token : dict
        The token response from the OAuth provider.
    provider : str
        The OAuth provider name.
    request : Request
        The incoming HTTP request.
    auth_service : AuthService
        Authentication service for user management.

    Returns
    -------
    Token
        JWT access and refresh tokens.

    Raises
    ------
    OAuthError
        If user processing fails.
    """
    try:
        user_info = await _get_user_info(client, token)
        user_timezone = await _detect_user_timezone(request)

        user = await auth_service.get_or_create_oauth_user(
            user_info,
            provider,
            timezone=user_timezone,
        )
        return auth_service.create_token_for_user(user)
    except OAuthError:
        raise
    except Exception as exc:
        logger.exception("OAuth user processing failed", extra={"provider": provider})
        details = f"OAuth user processing failed: {exc}"
        raise OAuthError(details) from exc


@dataclass(frozen=True)
class LoginOauthParams:
    client: OauthDep
    cache: CacheDep


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
)
@timed("/auth/login/oauth")
@limiter.limit("10/minute")
async def login_oauth(
    request: Request,
    response: Response,
    provider: str,
    deps: Annotated[LoginOauthParams, Depends()],
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
    deps : Annotated[LoginOauthParams, Depends()]
        Dependencies for the login handler.

    Returns
    -------
    RedirectResponse
        Redirects to the OAuth provider's authorization endpoint.

    Raises
    ------
    HTTPException
        If the provider is not configured.
    """

    # Generate cryptographically secure state parameter for CSRF protection
    state = token_urlsafe(32)

    # Store state in cache with TTL (single-use, expires after callback or timeout)
    state_key = f"oauth_state:{state}"
    await deps.cache.set(
        state_key,
        {"provider": provider, "ip": request.client.host if request.client else None},
        ttl=settings.OAUTH_STATE_EXPIRE_SECONDS,
    )

    redirect_uri = request.url_for("auth_callback", provider=provider)
    return await deps.client.authorize_redirect(request, redirect_uri, state=state)


@dataclass(frozen=True)
class CallbackParams:
    auth_service: AuthServiceDep
    oauth_client: OauthDep
    cache: CacheDep


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
    include_in_schema=True,
)
@timed("/auth/callback")
@limiter.limit("20/minute")
async def auth_callback(
    request: Request,
    response: Response,
    provider: str,
    deps: Annotated[CallbackParams, Depends()],
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
    deps : Annotated[CallbackParams, Depends()]
        Dependencies for the callback handler.

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

    state = request.query_params.get("state")
    oauth_client = deps.oauth_client
    await _validate_oauth_state(provider, state, deps.cache)

    token = await _exchange_oauth_token(oauth_client, request, provider)

    return await _process_oauth_user(oauth_client, token, provider, request, deps.auth_service)
