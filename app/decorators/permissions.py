"""
Permission decorators for route handlers.

These decorators provide an alternative to FastAPI dependencies for permission
checking. They are useful for legacy code or when you need to wrap existing
functions without modifying their signatures.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar
from uuid import UUID

from fastapi import HTTPException
from starlette.status import HTTP_403_FORBIDDEN

from app.auth.permissions import Permission, has_permission
from app.models import UserDB

F = TypeVar("F", bound=Callable)


def require_admin[F: Callable](func: F) -> F:
    """
    Admin role decorator for route handler.

    Parameters
    ----------
    func : F
        Route handler function.

    Returns
    -------
    F
    The decorated function must have a `user: UserDB` parameter.
    """

    @wraps(func)
    async def wrapper(*args, user: UserDB, **kwargs) -> Any:  # noqa: ANN002, ANN003, ANN401
        if user.role != "admin":
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )
        return await func(*args, user=user, **kwargs)

    return wrapper  # type: ignore[return-value]


def require_owner_or_admin(owner_id_getter: Callable[[], UUID]) -> Callable[[F], F]:
    """
    To require user is owner or admin.

    Args:
        owner_id_getter: Function to extract owner ID from route params/kwargs

    Returns:
        Decorator function

    Example:
        @router.put("/blogs/{blog_id}")
        @require_owner_or_admin(lambda **kwargs: kwargs.get('blog').author_id)
        async def update_blog(blog_id: UUID, user: UserDB, ...):
            ...
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, user: UserDB, **kwargs) -> Any:  # noqa: ANN002, ANN003, ANN401
            try:
                owner_id = owner_id_getter(*args, **kwargs)
            except (KeyError, AttributeError, TypeError):
                raise HTTPException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail="Could not determine resource owner",
                ) from None

            if user.uuid != owner_id and user.role != "admin":
                raise HTTPException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail="Owner or admin access required",
                )
            return await func(*args, user=user, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_permission_decorator(permission: Permission) -> Callable[[F], F]:
    """
    To require specific permission.

    Parameters
    ----------
    permission : Permission
        Required permission.

    Returns
    -------
    F
    The decorated function must have a `user: UserDB` parameter.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args, user: UserDB, **kwargs) -> Any:  # noqa: ANN002, ANN003, ANN401
            if not has_permission(user, permission):
                raise HTTPException(
                    status_code=HTTP_403_FORBIDDEN,
                    detail=f"Permission required: {permission.value}",
                )
            return await func(*args, user=user, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
