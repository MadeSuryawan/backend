"""Role-based access control (RBAC) permissions and dependencies."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from app.dependencies.dependencies import get_current_user
from app.models import UserDB

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


# Type aliases for common dependencies
AdminUserDep = Annotated[UserDB, Depends(require_admin)]
ModeratorUserDep = Annotated[UserDB, Depends(require_moderator)]
VerifiedUserDep = Annotated[UserDB, Depends(require_verified_user)]
