# app/routes/user.py

"""
User Routes.

Provides CRUD endpoints for user accounts with consistent documentation and
rate limiting aligned to established route patterns.

Summary
-------
Endpoints include:
  - Create user
  - Get all users
  - Get user by id
  - Get user by username
  - Update user
  - Delete user

Rate Limiting
-------------
All endpoints define explicit limits and include `429` response examples. Tiered
limits apply when `X-API-Key` is present, offering higher throughput for
authenticated/identified clients.
"""

from dataclasses import dataclass
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from app.configs import file_logger
from app.db import get_session
from app.decorators import cache_busting, cached, timed
from app.errors.base import host
from app.errors.database import DatabaseError, DuplicateEntryError
from app.managers import cache_manager, limiter
from app.models import UserDB
from app.repositories import UserRepository
from app.schemas import UserCreate, UserResponse, UserUpdate
from app.utils import response_datetime

router = APIRouter(prefix="/users", tags=["👤 Users"])

logger = file_logger(getLogger(__name__))


def db_user_to_response(db_user: UserDB) -> UserResponse:
    """
    Convert a `UserDB` instance to `UserResponse` with datetime serialization.

    Parameters
    ----------
    db_user : UserDB
        Database user entity.

    Returns
    -------
    UserResponse
        Validated response model.
    """

    user_dict = response_datetime(db_user)
    try:
        response = UserResponse.model_validate(user_dict, from_attributes=True)
    except ValidationError as e:
        mssg = f"Validation error converting user to response model: {e}"
        logger.exception("Validation error converting user to response model")
        raise ValueError(mssg) from e

    return response


def user_id_key(user_id: UUID) -> str:
    return f"user_by_id_{user_id}"


def username_key(username: str) -> str:
    return f"user_by_username_{username}"


def users_list_key(skip: int, limit: int) -> str:
    return f"users_all_{skip}_{limit}"


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


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
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


RepoDep = Annotated[UserRepository, Depends(get_user_repository)]


@router.post(
    "/create",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user account with the provided information.",
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
            "description": "Bad request",
            "content": {
                "application/json": {"example": {"detail": "Username or email already exists"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_create",
)
@timed("/users/create")
@limiter.limit(lambda key: "15/hour" if "apikey" in key else "3/hour")
@cache_busting(
    cache_manager,
    key_builder=lambda **kw: [users_list_key(0, 10)],
    namespace="users",
)
async def create_user(
    request: Request,
    response: Response,
    user: Annotated[
        UserCreate,
        Body(
            examples={
                "basic": {
                    "summary": "Basic user creation",
                    "value": {
                        "userName": "johndoe",
                        "firstName": "John",
                        "lastName": "Doe",
                        "email": "johndoe@gmail.com",
                        "password": "password123",
                        "bio": "Traveler and blogger",
                    },
                },
            },
        ),
    ],
    repo: RepoDep,
) -> UserResponse:
    """
    Create a new user and return the safe response model.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user : UserCreate
        User input payload.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    UserResponse
        Created user (without password).

    Raises
    ------
    HTTPException
        If username or email already exists.
    """
    try:
        db_user = await repo.create(user)
        await cache_manager.delete(
            user_id_key(db_user.uuid),
            username_key(db_user.username),
            namespace="users",
        )
        return db_user_to_response(db_user)
    except DuplicateEntryError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=e.detail) from e
    except DatabaseError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=e.detail) from e


@router.get(
    "/all",
    response_class=ORJSONResponse,
    response_model=list[UserResponse] | str,
    summary="Get all users",
    description="Retrieve a paginated list of all users.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "johndoe",
                            "firstName": "John",
                            "lastName": "Doe",
                            "email": "johndoe@gmail.com",
                            "isActive": True,
                            "isVerified": False,
                            "createdAt": "2025-01-01",
                            "updatedAt": "2025-01-01",
                        },
                    ],
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_get_all",
)
@timed("/users/all")
@limiter.limit(lambda key: "30/minute" if "apikey" in key else "10/minute")
@cached(
    cache_manager,
    ttl=3600,
    namespace="users",
    key_builder=lambda **kw: users_list_key(kw.get("skip", 0), kw.get("limit", 10)),
)
async def get_users(
    request: Request,
    response: Response,
    repo: RepoDep,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
) -> list[UserResponse] | str:
    """
    Get all users with pagination.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    list[UserResponse] | str
        List of users or informational message when none found.
    """
    db_users = await repo.get_all(skip=skip, limit=limit)
    if not db_users:
        return "No users found"
    return [db_user_to_response(user) for user in db_users]


@router.get(
    "/by-id/{user_id}",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Get user by ID",
    description="Retrieve a user by their UUID.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_get_by_id",
)
@timed("/users/by-id")
@limiter.limit(lambda key: "60/minute" if "apikey" in key else "20/minute")
@cached(
    cache_manager,
    ttl=1800,
    namespace="users",
    key_builder=lambda **kw: user_id_key(kw["user_id"]),
    response_model=UserResponse,
)
async def get_user(
    request: Request,
    response: Response,
    user_id: UUID,
    repo: RepoDep,
) -> UserResponse:
    """
    Get user by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    UserResponse
        User data without sensitive fields.

    Raises
    ------
    HTTPException
        If user not found.
    """
    db_user = await repo.get_by_id(user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    return db_user_to_response(db_user)


@router.get(
    "/by-username/{username}",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Get user by username",
    description="Retrieve a user by their username.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {
                    "example": {"detail": "User with username 'johndoe' not found"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_get_by_username",
)
@timed("/users/by-username")
@limiter.limit(lambda key: "60/minute" if "apikey" in key else "20/minute")
@cached(
    cache_manager,
    ttl=1800,
    namespace="users",
    key_builder=lambda **kw: username_key(kw["username"]),
    response_model=UserResponse,
)
async def get_user_by_username(
    request: Request,
    response: Response,
    username: str,
    repo: RepoDep,
) -> UserResponse:
    """
    Get user by username.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    username : str
        Username value.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    UserResponse
        User data without sensitive fields.

    Raises
    ------
    HTTPException
        If user not found.
    """
    db_user = await repo.get_by_username(username)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with username '{username}' not found",
        )
    return db_user_to_response(db_user)


@router.put(
    "/update/{user_id}",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Update user",
    description="Update user information. Only provided fields will be updated.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {"application/json": {"example": {"detail": "Email already exists"}}},
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_update",
)
@timed("/users/update")
@limiter.limit(lambda key: "20/minute" if "apikey" in key else "5/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda user_id, **kw: [user_id_key(user_id), users_list_key(0, 10)],
    namespace="users",
)
async def update_user(
    request: Request,
    response: Response,
    user_id: UUID,
    user_update: Annotated[
        UserUpdate,
        Body(
            examples={
                "basic": {
                    "summary": "Update display fields",
                    "value": {
                        "firstName": "Johnny",
                        "lastName": "D",
                        "bio": "Globetrotter",
                    },
                },
            },
        ),
    ],
    repo: RepoDep,
) -> UserResponse:
    """
    Update user information and return the safe response model.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier.
    user_update : UserUpdate
        Update payload (partial updates accepted).
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    UserResponse
        Updated user without sensitive fields.

    Raises
    ------
    HTTPException
        If user not found or invalid update.
    """
    try:
        existing = await repo.get_by_id(user_id)
        db_user = await repo.update(user_id, user_update)
        if not db_user:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found",
            )
        keys: list[str] = []
        if existing:
            keys.extend(
                [
                    user_id_key(existing.uuid),
                    username_key(existing.username),
                    users_list_key(0, 10),
                ],
            )
        keys.extend(
            [
                user_id_key(db_user.uuid),
                username_key(db_user.username),
                users_list_key(0, 10),
            ],
        )
        await cache_manager.delete(*keys, namespace="users")
        return db_user_to_response(db_user)
    except DuplicateEntryError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=e.detail) from e
    except DatabaseError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=e.detail) from e


@router.delete(
    "/delete/{user_id}",
    response_class=ORJSONResponse,
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user by their UUID.",
    responses={
        204: {"description": "No Content"},
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_delete",
)
@timed("/users/delete")
@limiter.limit(lambda key: "10/minute" if "apikey" in key else "2/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda user_id, **kw: [user_id_key(user_id), users_list_key(0, 10)],
    namespace="users",
)
async def delete_user(
    request: Request,
    response: Response,
    user_id: UUID,
    repo: RepoDep,
) -> None:
    """
    Delete user by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier.
    repo : UserRepository
        Repository dependency.

    Raises
    ------
    HTTPException
        If user not found.
    """
    existing = await repo.get_by_id(user_id)
    deleted = await repo.delete(user_id)
    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    if existing:
        await cache_manager.delete(
            user_id_key(existing.uuid),
            username_key(existing.username),
            users_list_key(0, 10),
            namespace="users",
        )


@router.post(
    "/bust-list",
    response_class=ORJSONResponse,
    summary="Bust users list cache page",
    description="Invalidate cached users list page for given `skip` and `limit`.",
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_list",
)
@timed("/users/bust-list")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda **kw: [users_list_key(kw.get("skip", 0), kw.get("limit", 10))],
    namespace="users",
)
async def bust_users_list(
    request: Request,
    response: Response,
    *,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip.")],
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return.")],
) -> ORJSONResponse:
    """
    Bust users list cache page.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.
    """
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-by-id",
    response_class=ORJSONResponse,
    summary="Bust cached user by ID",
    description="Invalidate cached user detail for a given UUID.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required (localhost only)"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_by_id",
)
@timed("/users/bust-by-id")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda user_id, **kw: [user_id_key(user_id)],
    namespace="users",
)
async def bust_user_by_id(
    request: Request,
    response: Response,
    user_id: UUID,
) -> ORJSONResponse:
    if host(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-by-username",
    response_class=ORJSONResponse,
    summary="Bust cached user by username",
    description="Invalidate cached user detail for a given username.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required (localhost only)"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_by_username",
)
@timed("/users/bust-by-username")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda username, **kw: [username_key(username)],
    namespace="users",
)
async def bust_user_by_username(
    request: Request,
    response: Response,
    username: str,
) -> ORJSONResponse:
    if host(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-list-multi",
    response_class=ORJSONResponse,
    summary="Bust multiple users list cache pages",
    description="Invalidate cached users list pages across multiple `limit` values.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required (localhost only)"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_list_multi",
)
@timed("/users/bust-list-multi")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda query, limits, **kw: [
        users_list_key(query.skip, limit_value) for limit_value in limits
    ],
    namespace="users",
)
async def bust_users_list_multi(
    request: Request,
    response: Response,
    query: Annotated[UserListQuery, Depends(get_user_list_query)],
    limits: Annotated[list[int], Query(description="List of limit values to invalidate.")],
) -> ORJSONResponse:
    if host(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-list-grid",
    response_class=ORJSONResponse,
    summary="Bust users list pages across limits and skips",
    description="Invalidate cached users list pages across multiple `limit` and `skip` values.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required (localhost only)"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_list_grid",
)
@timed("/users/bust-list-grid")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda query, limits, skips, **kw: [
        users_list_key(skip_value, limit_value) for limit_value in limits for skip_value in skips
    ],
    namespace="users",
)
async def bust_users_list_grid(
    request: Request,
    response: Response,
    query: Annotated[UserListQuery, Depends(get_user_list_query)],
    limits: Annotated[list[int], Query(description="List of limit values to invalidate.")],
    skips: Annotated[list[int], Query(description="List of skip values to invalidate.")],
) -> ORJSONResponse:
    if host(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )
    return ORJSONResponse(content={"status": "success"})


@router.delete(
    "/bust-all",
    response_class=ORJSONResponse,
    summary="Clear users cache namespace",
    description="Clear all cached keys in the users namespace.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "cleared"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required (localhost only)"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_all",
)
@timed("/users/bust-all")
@limiter.limit("5/minute")
async def bust_users_all(request: Request, response: Response) -> ORJSONResponse:
    if host(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )
    await cache_manager.clear(namespace="users")
    return ORJSONResponse(content={"status": "cleared"})
