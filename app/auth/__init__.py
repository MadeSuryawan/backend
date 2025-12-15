"""Authentication and authorization module."""

from app.auth.permissions import (
    AdminUserDep,
    ModeratorUserDep,
    VerifiedUserDep,
    has_role_or_higher,
    require_admin,
    require_moderator,
    require_role,
    require_role_or_higher,
    require_verified_user,
)

__all__ = [
    "AdminUserDep",
    "ModeratorUserDep",
    "VerifiedUserDep",
    "has_role_or_higher",
    "require_admin",
    "require_moderator",
    "require_role",
    "require_role_or_higher",
    "require_verified_user",
]
