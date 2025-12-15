"""
Admin Routes.

Endpoints for administrative operations requiring admin role.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from app.auth.permissions import AdminUserDep
from app.db import get_session
from app.decorators.metrics import timed
from app.dependencies import UserRepoDep
from app.models import UserDB
from app.schemas.admin import (
    AdminUserListResponse,
    AdminUserResponse,
    SystemStatsResponse,
    UserRoleUpdate,
)
from app.schemas.user import UserResponse

router = APIRouter(prefix="/admin", tags=["👑 Admin"])


@router.get(
    "/users",
    response_class=ORJSONResponse,
    response_model=AdminUserListResponse,
    summary="List all users (admin only)",
    description="Retrieve paginated list of all users. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "users": [
                            {
                                "id": "123e4567-e89b-12d3-a456-426614174000",
                                "username": "johndoe",
                                "email": "johndoe@gmail.com",
                                "isActive": True,
                                "isVerified": False,
                            },
                        ],
                        "total": 100,
                        "skip": 0,
                        "limit": 10,
                    },
                },
            },
        },
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {"example": {"detail": "Admin access required"}},
            },
        },
    },
    operation_id="admin_list_users",
)
@timed("/admin/users")
async def list_all_users(
    admin_user: AdminUserDep,
    repo: UserRepoDep,
    session: Annotated[AsyncSession, Depends(get_session)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
) -> AdminUserListResponse:
    """
    List all users with pagination.

    Parameters
    ----------
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).
    repo : UserRepository
        User repository dependency.
    session : AsyncSession
        Database session for counting total users.

    Returns
    -------
    AdminUserListResponse
        Paginated list of users with total count.
    """
    users = await repo.get_all(skip=skip, limit=limit)

    # Get total count
    result = await session.execute(select(func.count()).select_from(UserDB))
    total = result.scalar_one() or 0

    return AdminUserListResponse(
        users=[UserResponse.model_validate(user) for user in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/users/{user_id}",
    response_class=ORJSONResponse,
    response_model=AdminUserResponse,
    summary="Get user details (admin only)",
    description="Get detailed user information including role. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "role": "user",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User not found"}},
            },
        },
    },
    operation_id="admin_get_user",
)
@timed("/admin/users/{user_id}")
async def get_user_details(
    user_id: UUID,
    admin_user: AdminUserDep,
    repo: UserRepoDep,
) -> AdminUserResponse:
    """
    Get user details by ID.

    Parameters
    ----------
    user_id : UUID
        User identifier.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).
    repo : UserRepository
        User repository dependency.
    session : AsyncSession
        Database session for committing role update.

    Returns
    -------
    AdminUserResponse
        User details including role.

    Raises
    ------
    HTTPException
        If user not found.
    """
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserResponse.model_validate(user)


@router.put(
    "/users/{user_id}/role",
    response_class=ORJSONResponse,
    response_model=AdminUserResponse,
    summary="Update user role (admin only)",
    description="Update a user's role. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "role": "moderator",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {
                "application/json": {"example": {"detail": "Invalid role"}},
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User not found"}},
            },
        },
    },
    operation_id="admin_update_user_role",
)
@timed("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: UUID,
    role_update: UserRoleUpdate,
    admin_user: AdminUserDep,
    repo: UserRepoDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminUserResponse:
    """
    Update user role.

    Parameters
    ----------
    user_id : UUID
        User identifier.
    role_update : UserRoleUpdate
        New role value.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).
    repo : UserRepository
        User repository dependency.
    session : AsyncSession
        Database session for committing role update.

    Returns
    -------
    AdminUserResponse
        Updated user with new role.

    Raises
    ------
    HTTPException
        If user not found or invalid role.
    """
    if role_update.role not in ("user", "moderator", "admin"):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="Invalid role. Must be one of: user, moderator, admin",
        )

    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="User not found")

    # Update role directly
    user.role = role_update.role
    user.updated_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(user)
    return AdminUserResponse.model_validate(user)


@router.get(
    "/stats",
    response_class=ORJSONResponse,
    response_model=SystemStatsResponse,
    summary="Get system statistics (admin only)",
    description="Retrieve system-wide statistics. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "total_users": 150,
                        "active_users": 120,
                        "verified_users": 100,
                        "admin_users": 3,
                        "moderator_users": 5,
                    },
                },
            },
        },
    },
    operation_id="admin_get_stats",
)
@timed("/admin/stats")
async def get_system_stats(
    admin_user: AdminUserDep,
    repo: UserRepoDep,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SystemStatsResponse:
    """
    Get system statistics.

    Parameters
    ----------
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).
    repo : UserRepository
        User repository dependency.
    session : AsyncSession
        Database session for querying statistics.

    Returns
    -------
    SystemStatsResponse
        System-wide statistics.
    """
    # Get total users
    total_result = await session.execute(select(func.count()).select_from(UserDB))
    total_users = total_result.scalar_one() or 0

    # Get active users - use get_all and filter in Python for simplicity
    all_users = await repo.get_all(skip=0, limit=10000)  # Get all users
    active_users = sum(1 for u in all_users if u.is_active)
    verified_users = sum(1 for u in all_users if u.is_verified)
    admin_users = sum(1 for u in all_users if u.role == "admin")
    moderator_users = sum(1 for u in all_users if u.role == "moderator")

    return SystemStatsResponse(
        total_users=total_users,
        active_users=active_users,
        verified_users=verified_users,
        admin_users=admin_users,
        moderator_users=moderator_users,
    )
