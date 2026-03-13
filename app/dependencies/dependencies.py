# app/dependencies/dependencies.py

"""Application dependencies with enhanced authentication."""

from contextlib import suppress
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from authlib.integrations.starlette_client import OAuth
from authlib.integrations.starlette_client import StarletteOAuth2App as OAuthClient
from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
)

from app.clients.ai_client import AiClient
from app.clients.email_client import EmailClient
from app.clients.redis_client import RedisClient
from app.configs.settings import settings
from app.db import get_session
from app.managers.cache_manager import CacheManager
from app.managers.login_attempt_tracker import LoginAttemptTracker
from app.managers.password_manager import Argon2Hasher
from app.managers.token_blacklist import TokenBlacklist
from app.managers.token_manager import decode_access_token
from app.models import UserDB
from app.monitoring import HealthChecker
from app.repositories import BlogRepository, ReviewRepository, UserRepository
from app.schemas.user import UserResponse, validate_user_response
from app.services import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_health_checker(request: Request) -> HealthChecker:
    """Dependency to get the global health checker instance."""
    return request.app.state.health_checker


HealthCheckerDep = Annotated[HealthChecker, Depends(get_health_checker)]


def get_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthService:
    """
    Dependency to get AuthService with optional blacklist and tracker.

    Falls back gracefully if Redis-based managers are not initialized.
    """
    repo = UserRepository(session)

    blacklist: TokenBlacklist | None = None
    login_tracker: LoginAttemptTracker | None = None
    redis_client: RedisClient | None = None

    with suppress(AttributeError):
        blacklist = request.app.state.token_blacklist
        login_tracker = request.app.state.login_tracker
        redis_client = blacklist.redis_client

    return AuthService(
        repo,
        token_blacklist=blacklist,
        login_tracker=login_tracker,
        redis_client=redis_client,
        email_client=EmailClient(),
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_password_hasher(request: Request) -> Argon2Hasher:
    """Dependency to get the password hasher instance."""
    return request.app.state.password_hasher


PasswordHasherDep = Annotated[Argon2Hasher, Depends(get_password_hasher)]

# OAuth Configuration
oauth = OAuth()

PROVIDER_NOT_FOUND = (
    "This sign-in method is not available right now. Please try a different sign-in option."
)

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


def get_oauth_client(provider: str) -> OAuthClient:
    """
    Get OAuth client for the specified provider.

    Parameters
    ----------
    provider : str
        The OAuth provider name (e.g., 'google', 'wechat').

    Returns
    -------
    OAuthClient
        The configured OAuth client for the provider.

    Raises
    ------
    HTTPException
        If the provider is not configured.
    """
    client = oauth.create_client(provider)
    if not client:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=PROVIDER_NOT_FOUND,
        )
    return client


OauthDep = Annotated[OAuthClient, Depends(get_oauth_client)]


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDB:
    """
    Get current authenticated user using user_id from token claims.

    Enhanced to use user_id for efficient lookup and check token blacklist.

    Parameters
    ----------
    request : Request
        Current request context.
    token : str
        Bearer token.
    session : AsyncSession
        Database session.

    Returns
    -------
    UserDB
        Current authenticated user.
    """
    token_data = decode_access_token(token)
    if not token_data:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hasattr(request.app.state, "token_blacklist"):
        blacklist: TokenBlacklist = request.app.state.token_blacklist
        is_blacklisted = await blacklist.is_blacklisted(token_data.jti)
        if is_blacklisted:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Your session has been signed out. Please sign in again to continue.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Use user_id for efficient lookup (no username index scan)
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(token_data.user_id)

    if not user:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="We couldn't find your account. It may have been removed or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request.state.user_id = str(token_data.user_id)
    return user


def get_user_repository(session: Annotated[AsyncSession, Depends(get_session)]) -> UserRepository:
    """
    Resolve the `UserRepository` dependency.

    Parameters
    ----------
    session : AsyncSession
        Database session.

    Returns
    -------
    UserRepository
        Repository instance bound to the session.
    """
    return UserRepository(session)


async def get_current_user_response(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """
    Get current authenticated user as a response DTO (without sensitive data).

    This dependency should be used for routes that return user data to ensure
    password_hash and other sensitive fields are not exposed in the response.

    Parameters
    ----------
    request : Request
        Current request context.
    token : str
        Bearer token.
    session : AsyncSession
        Database session.

    Returns
    -------
    UserResponse
        Current authenticated user as a safe response model.
    """
    user_db = await get_current_user(request, token, session)
    return validate_user_response(user_db)


UserDBDep = Annotated[UserDB, Depends(get_current_user)]
UserRespDep = Annotated[UserResponse, Depends(get_current_user_response)]
UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]


async def is_admin(
    user: Annotated[UserDB, Depends(get_current_user)],
) -> UserDB:
    """
    Dependency that requires admin role.

    Parameters
    ----------
    user : UserDB
        Current authenticated user.

    Returns
    -------
    UserDB
        The user if they have admin role.

    Raises
    ------
    HTTPException
        If user is not an admin.
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Sorry, you don't have permission to access this feature. This area is reserved for admin users only.",
        )
    return user


async def is_moderator(
    user: Annotated[UserDB, Depends(get_current_user)],
) -> UserDB:
    """
    Dependency that requires moderator role.

    Parameters
    ----------
    user : UserDB
        Current authenticated user.

    Returns
    -------
    UserDB
        The user if they have moderator role.

    Raises
    ------
    HTTPException
        If user is not a moderator.
    """
    if user.role != "moderator":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Moderator access required",
        )
    return user


async def is_verified(
    user: Annotated[UserDB, Depends(get_current_user)],
) -> UserDB:
    """
    Get current authenticated and verified user.

    Parameters
    ----------
    user : UserDB
        Current user from get_current_user.

    Returns
    -------
    UserDB
        Current verified user.

    Raises
    ------
    HTTPException
        If user email is not verified.
    """
    if not user.is_verified:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Your email address hasn't been verified yet. Please check your inbox for a verification email or request a new one to unlock your account.",
        )
    return user


AdminUserDep = Annotated[UserDB, Depends(is_admin)]
ModeratorUserDep = Annotated[UserDB, Depends(is_moderator)]
VerifiedUserDep = Annotated[UserDB, Depends(is_verified)]


async def get_user_or_404(repo: UserRepoDep, user_id: UUID) -> UserDB:
    """
    Retrieve user by ID or raise 404 if not found.

    Parameters
    ----------
    repo : UserRepoDep
        User repository instance.
    user_id : UUID
        User identifier.

    Returns
    -------
    UserDB
        The user database entity.

    Raises
    ------
    HTTPException
        404 if user not found.
    """
    db_user = await repo.get_by_id(user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    return db_user


def check_owner_or_admin(
    owner_id: UUID,
    current_user: UserDB,
    resource_name: str = "resource",
) -> None:
    """
    Check if user is owner or admin, raise exception if not.

    Args:
        owner_id: UUID of the resource owner
        current_user: Current authenticated user
        resource_name: Name of resource for error message

    Raises:
        HTTPException: If user is not owner or admin
    """
    if current_user.uuid != owner_id and current_user.role != "admin":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail=f"Sorry, you can only manage your own {resource_name}. Please contact an admin if you need assistance.",
        )


async def get_authorized_user(
    repo: UserRepoDep,
    user_id: UUID,
    current_user: UserDB,
    resource_name: str = "user",
) -> UserDB:
    """
    Retrieve user and verify authorization (owner or admin).

    Parameters
    ----------
    repo : UserRepoDep
        User repository instance.
    user_id : UUID
        Target user identifier.
    current_user : UserDB
        Currently authenticated user.
    resource_name : str
        Resource name for error messages.

    Returns
    -------
    UserDB
        The authorized user database entity.

    Raises
    ------
    HTTPException
        404 if user not found, 403 if not authorized.
    """
    db_user = await get_user_or_404(repo, user_id)
    check_owner_or_admin(user_id, current_user, resource_name)
    return db_user


def get_blog_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BlogRepository:
    """
    Resolve the `BlogRepository` dependency.

    Parameters
    ----------
    session : AsyncSession
        Database session.

    Returns
    -------
    BlogRepository
        Repository instance bound to the session.
    """
    return BlogRepository(session)


BlogRepoDep = Annotated[BlogRepository, Depends(get_blog_repository)]


async def get_review_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewRepository:
    """
    Dependency to get ReviewRepository.

    Parameters
    ----------
    session : AsyncSession
        Database session from dependency injection.

    Returns
    -------
    ReviewRepository
        Repository instance bound to the session.
    """
    return ReviewRepository(session)


ReviewRepoDep = Annotated[ReviewRepository, Depends(get_review_repository)]


@dataclass(frozen=True)
class UserListQuery:
    skip: int = 0
    limit: int = 10


def get_user_list_query(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
) -> UserListQuery:
    return UserListQuery(skip=skip, limit=limit)


UserQueryListDep = Annotated[UserListQuery, Depends(get_user_list_query)]


@dataclass(frozen=True)
class BlogListQuery:
    """
    Query container for blog listing and filters.

    Parameters
    ----------
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    status_filter : Literal | None
        Optional status filter.
    author_id : UUID | None
        Optional author filter.
    """

    skip: int = 0
    limit: int = 10
    status_filter: Literal["draft", "published", "archived"] | None = None
    author_id: UUID | None = None


def get_blog_list_query(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
    status_filter: Annotated[
        Literal["draft", "published", "archived"] | None,
        Query(alias="status", description="Optional status filter"),
    ] = None,
    author_id: Annotated[UUID | None, Query(description="Optional author ID filter")] = None,
) -> BlogListQuery:
    """
    Dependency to construct `BlogListQuery` from query parameters.

    Returns
    -------
    BlogListQuery
        Aggregated query parameters object.
    """
    return BlogListQuery(
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        author_id=author_id,
    )


BlogQueryListDep = Annotated[BlogListQuery, Depends(get_blog_list_query)]


def get_cache_manager(request: Request) -> CacheManager:
    """Dependency to get the global cache manager instance."""
    return request.app.state.cache_manager


CacheDep = Annotated[CacheManager, Depends(get_cache_manager)]


def get_email_client() -> EmailClient:
    return EmailClient()


EmailDep = Annotated[EmailClient, Depends(get_email_client)]


def get_ai_client_state(request: Request) -> AiClient:
    return request.app.state.ai_client


AiDep = Annotated[AiClient, Depends(get_ai_client_state)]
