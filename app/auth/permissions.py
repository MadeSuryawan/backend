"""Role-based access control (RBAC) permissions and dependencies."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from app.dependencies.dependencies import get_current_user
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


async def require_admin(
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
            detail="Admin access required",
        )
    return user


async def require_moderator(
    user: Annotated[UserDB, Depends(get_current_user)],
) -> UserDB:
    """
    Dependency that requires moderator role or higher.

    Parameters
    ----------
    user : UserDB
        Current authenticated user.

    Returns
    -------
    UserDB
        The user if they have moderator role or higher.

    Raises
    ------
    HTTPException
        If user doesn't have sufficient permissions.
    """
    if not has_role_or_higher(user.role, "moderator"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Moderator access required",
        )
    return user


async def require_verified_user(
    user: Annotated[UserDB, Depends(get_current_user)],
) -> UserDB:
    """
    Dependency that requires email-verified user.

    Parameters
    ----------
    user : UserDB
        Current authenticated user.

    Returns
    -------
    UserDB
        The user if their email is verified.

    Raises
    ------
    HTTPException
        If user email is not verified.
    """
    if not user.is_verified:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email first.",
        )
    return user


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
            detail=f"Only the {resource_name} owner or admin can perform this action",
        )


# Type aliases for common dependencies
AdminUserDep = Annotated[UserDB, Depends(require_admin)]
ModeratorUserDep = Annotated[UserDB, Depends(require_moderator)]
VerifiedUserDep = Annotated[UserDB, Depends(require_verified_user)]
