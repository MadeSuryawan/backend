"""Role-based access control (RBAC) permissions."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from app.dependencies import get_current_user
from app.models import UserDB


class Permission(StrEnum):
    """Granular permissions for fine-grained access control."""

    # Read permissions
    READ_USERS = "read:users"
    READ_BLOGS = "read:blogs"
    READ_ADMIN = "read:admin"

    # Write permissions
    WRITE_BLOGS = "write:blogs"
    WRITE_USERS = "write:users"

    # Delete permissions
    DELETE_BLOGS = "delete:blogs"
    DELETE_USERS = "delete:users"

    # Admin permissions
    ADMIN_ALL = "admin:all"


# Role-permission mapping: defines what permissions each role has
ROLE_PERMISSIONS: dict[str, list[Permission]] = {
    "user": [
        Permission.READ_BLOGS,
        Permission.WRITE_BLOGS,  # Own blogs only (enforced at route level)
    ],
    "moderator": [
        Permission.READ_USERS,
        Permission.READ_BLOGS,
        Permission.WRITE_BLOGS,
        Permission.DELETE_BLOGS,  # Any blog
    ],
    "admin": [
        Permission.READ_USERS,
        Permission.READ_BLOGS,
        Permission.READ_ADMIN,
        Permission.WRITE_BLOGS,
        Permission.WRITE_USERS,
        Permission.DELETE_BLOGS,
        Permission.DELETE_USERS,
        Permission.ADMIN_ALL,
    ],
}

# Define role hierarchy (higher index = more permissions)
ROLE_HIERARCHY = {
    "user": 0,
    "moderator": 1,
    "admin": 2,
}


def has_role_or_higher(user_role: str, required_role: str) -> bool:
    """
    Check if user has the required role or higher.

    Args:
        user_role: User's current role
        required_role: Required role for access

    Returns:
        bool: True if user has required role or higher
    """
    user_level = ROLE_HIERARCHY.get(user_role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level


def require_role(roles: list[str]) -> Callable[..., Awaitable[UserDB]]:
    """
    Create a dependency that requires specific roles.

    Args:
        roles: List of allowed roles

    Returns:
        Callable: Dependency function

    Example:
        @router.get("/admin-only")
        async def admin_route(user: Annotated[UserDB, Depends(require_role(["admin"]))]):
            ...
    """

    async def role_checker(
        user: Annotated[UserDB, Depends(get_current_user)],
    ) -> UserDB:
        if user.role not in roles:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(roles)}",
            )
        return user

    return role_checker


def require_role_or_higher(required_role: str) -> Callable[..., Awaitable[UserDB]]:
    """
    Create a dependency that requires a role or higher in hierarchy.

    Args:
        required_role: Minimum required role

    Returns:
        Callable: Dependency function

    Example:
        @router.get("/mod-plus")
        async def mod_route(user: Annotated[UserDB, Depends(require_role_or_higher("moderator"))]):
            ...
    """

    async def role_checker(
        user: Annotated[UserDB, Depends(get_current_user)],
    ) -> UserDB:
        if not has_role_or_higher(user.role, required_role):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role} or higher",
            )
        return user

    return role_checker


def has_permission(user: UserDB, permission: Permission) -> bool:
    """
    Check if user has a specific permission.

    Args:
        user: User to check permissions for
        permission: Permission to check

    Returns:
        bool: True if user has the permission, False otherwise
    """
    user_permissions = ROLE_PERMISSIONS.get(user.role, [])
    return permission in user_permissions or Permission.ADMIN_ALL in user_permissions


def require_permission(permission: Permission) -> Callable[..., Awaitable[UserDB]]:
    """
    Create a dependency that requires a specific permission.

    Args:
        permission: Required permission

    Returns:
        Callable: Dependency function that checks permission

    Example:
        @router.get("/admin-only")
        async def admin_route(
            user: Annotated[UserDB, Depends(require_permission(Permission.ADMIN_ALL))]
        ):
            ...
    """

    async def permission_checker(
        user: Annotated[UserDB, Depends(get_current_user)],
    ) -> UserDB:
        if not has_permission(user, permission):
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission.value}",
            )
        return user

    return permission_checker
