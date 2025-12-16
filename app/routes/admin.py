"""
Admin Routes.

Endpoints for administrative operations requiring admin role.
"""

from contextlib import suppress
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
from app.dependencies import IdempotencyDep, UserRepoDep, get_idempotency_manager
from app.models import UserDB
from app.schemas.admin import (
    AdminUserListResponse,
    AdminUserResponse,
    SystemStatsResponse,
    UserRoleUpdate,
)
from app.schemas.idempotency import IdempotencyMetrics, IdempotencyRecord
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


# =============================================================================
# Idempotency Management Endpoints
# =============================================================================


@router.get(
    "/idempotency/metrics",
    response_class=ORJSONResponse,
    response_model=IdempotencyMetrics,
    summary="Get idempotency metrics (admin only)",
    description="Retrieve idempotency hit/miss statistics. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "hits": 150,
                        "misses": 500,
                        "blocked_duplicates": 25,
                        "hit_rate": 0.23,
                    },
                },
            },
        },
        503: {
            "description": "Idempotency manager not available",
            "content": {
                "application/json": {"example": {"detail": "Idempotency manager not initialized"}},
            },
        },
    },
    operation_id="admin_get_idempotency_metrics",
)
@timed("/admin/idempotency/metrics")
async def get_idempotency_metrics(
    admin_user: AdminUserDep,
) -> IdempotencyMetrics:
    """
    Get idempotency hit/miss metrics.

    Parameters
    ----------
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    IdempotencyMetrics
        Statistics about idempotency cache hits, misses, and blocked duplicates.
    """
    try:
        manager = get_idempotency_manager()
        return manager.get_metrics()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get(
    "/idempotency/keys/{idempotency_key}",
    response_class=ORJSONResponse,
    response_model=IdempotencyRecord | None,
    summary="Get idempotency record (admin only)",
    description="Retrieve an idempotency record by key. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "key": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "COMPLETED",
                        "response": {"id": "123", "name": "test"},
                        "created_at": "2025-01-01T12:00:00Z",
                        "ttl_seconds": 3600,
                    },
                },
            },
        },
        404: {
            "description": "Key not found",
            "content": {
                "application/json": {"example": {"detail": "Idempotency key not found"}},
            },
        },
        503: {
            "description": "Idempotency manager not available",
            "content": {
                "application/json": {"example": {"detail": "Idempotency manager not initialized"}},
            },
        },
    },
    operation_id="admin_get_idempotency_record",
)
@timed("/admin/idempotency/keys/{idempotency_key}")
async def get_idempotency_record(
    idempotency_key: str,
    admin_user: AdminUserDep,
) -> IdempotencyRecord | None:
    """
    Get an idempotency record by key.

    Parameters
    ----------
    idempotency_key : str
        The idempotency key to look up.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    IdempotencyRecord | None
        The idempotency record if found, None otherwise.
    """
    try:
        manager = get_idempotency_manager()
        record = await manager.get_record_by_key(idempotency_key)
        if record is None:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Idempotency key not found")
        return record
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.delete(
    "/idempotency/keys/{idempotency_key}",
    response_class=ORJSONResponse,
    summary="Delete idempotency key (admin only)",
    description="Delete an idempotency record by key. Admin access required.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "deleted", "key": "550e8400-e29b-41d4-a716-446655440000"},
                },
            },
        },
        404: {
            "description": "Key not found",
            "content": {
                "application/json": {"example": {"detail": "Idempotency key not found"}},
            },
        },
        503: {
            "description": "Idempotency manager not available",
            "content": {
                "application/json": {"example": {"detail": "Idempotency manager not initialized"}},
            },
        },
    },
    operation_id="admin_delete_idempotency_key",
)
@timed("/admin/idempotency/keys/{idempotency_key}")
async def delete_idempotency_key(
    idempotency_key: str,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Delete an idempotency record.

    This allows administrators to clear idempotency keys that may be
    blocking legitimate retries.

    Parameters
    ----------
    idempotency_key : str
        The idempotency key to delete.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Confirmation of deletion.
    """
    try:
        manager = get_idempotency_manager()
        deleted = await manager.delete_key(idempotency_key)
        if not deleted:
            raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Idempotency key not found")
        return ORJSONResponse(content={"status": "deleted", "key": idempotency_key})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.delete(
    "/idempotency/clear",
    response_class=ORJSONResponse,
    summary="Clear all idempotency keys (admin only)",
    description="Clear all idempotency records. Admin access required. Use with caution.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "cleared", "count": 42},
                },
            },
        },
        503: {
            "description": "Idempotency manager not available",
            "content": {
                "application/json": {"example": {"detail": "Idempotency manager not initialized"}},
            },
        },
    },
    operation_id="admin_clear_idempotency_keys",
)
@timed("/admin/idempotency/clear")
async def clear_all_idempotency_keys(
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Clear all idempotency records.

    WARNING: This will allow previously-blocked duplicate requests to be
    processed again. Use with caution.

    Parameters
    ----------
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Confirmation with count of cleared records.
    """
    try:
        manager = get_idempotency_manager()
        count = await manager.clear_all()
        return ORJSONResponse(content={"status": "cleared", "count": count})
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
