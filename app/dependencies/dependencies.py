# app/dependencies/dependencies.py

"""Application dependencies with enhanced authentication."""

from contextlib import suppress
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from app.clients.ai_client import AiClient
from app.clients.email_client import EmailClient
from app.db import get_session
from app.managers.cache_manager import CacheManager
from app.managers.login_attempt_tracker import LoginAttemptTracker, get_login_tracker
from app.managers.token_blacklist import TokenBlacklist, get_token_blacklist
from app.managers.token_manager import decode_access_token
from app.models import UserDB
from app.repositories import BlogRepository, UserRepository
from app.schemas.user import UserResponse
from app.services import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    request: Request,
) -> AuthService:
    """
    Dependency to get AuthService with optional blacklist and tracker.

    Falls back gracefully if Redis-based managers are not initialized.
    """
    repo = UserRepository(session)

    # Try to get blacklist and tracker, but don't fail if not available
    blacklist: TokenBlacklist | None = None
    tracker: LoginAttemptTracker | None = None

    with suppress(RuntimeError):
        blacklist = get_token_blacklist()

    with suppress(RuntimeError):
        tracker = get_login_tracker()

    return AuthService(repo, token_blacklist=blacklist, login_tracker=tracker)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserDB:
    """
    Get current authenticated user using user_id from token claims.

    Enhanced to use user_id for efficient lookup and check token blacklist.

    Parameters
    ----------
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

    # Check token blacklist if available
    try:
        blacklist = get_token_blacklist()
        is_blacklisted = await blacklist.is_blacklisted(token_data.jti)
        if is_blacklisted:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except RuntimeError:
        pass  # Blacklist not initialized, skip check

    # Use user_id for efficient lookup (no username index scan)
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(token_data.user_id)

    if not user:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="Inactive user")

    return user


async def get_verified_user(
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
            detail="Email not verified. Please verify your email first.",
        )
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


UserDBDep = Annotated[UserDB, Depends(get_current_user)]
UserRespDep = Annotated[UserResponse, Depends(get_current_user)]
VerifiedUserDep = Annotated[UserDB, Depends(get_verified_user)]
UserRepoDep = Annotated[UserRepository, Depends(get_user_repository)]


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
