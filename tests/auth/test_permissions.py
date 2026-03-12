"""Tests for RBAC permissions and dependencies."""

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import UserDB
from app.rabc import (
    ROLE_HIERARCHY,
    Permission,
    has_permission,
    has_role_or_higher,
    require_permission,
    require_role,
    require_role_or_higher,
)


def _make_user(role: str) -> UserDB:
    """Create a minimal user for RBAC tests."""
    return UserDB(
        uuid=uuid4(),
        username=f"{role}user",
        email=f"{role}@example.com",
        role=role,
        is_verified=True,
    )


class TestRoleHierarchy:
    """Test cases for role hierarchy."""

    def test_hierarchy_contains_expected_roles(self) -> None:
        """Test that role hierarchy contains all expected roles."""
        assert "user" in ROLE_HIERARCHY
        assert "moderator" in ROLE_HIERARCHY
        assert "admin" in ROLE_HIERARCHY

    def test_hierarchy_order_is_correct(self) -> None:
        """Test that hierarchy order is user < moderator < admin."""
        assert ROLE_HIERARCHY["user"] < ROLE_HIERARCHY["moderator"]
        assert ROLE_HIERARCHY["moderator"] < ROLE_HIERARCHY["admin"]


class TestHasRoleOrHigher:
    """Test cases for has_role_or_higher function."""

    def test_user_has_user_role(self) -> None:
        """Test that user role satisfies user requirement."""
        assert has_role_or_higher("user", "user") is True

    def test_user_does_not_have_moderator(self) -> None:
        """Test that user role does not satisfy moderator requirement."""
        assert has_role_or_higher("user", "moderator") is False

    def test_user_does_not_have_admin(self) -> None:
        """Test that user role does not satisfy admin requirement."""
        assert has_role_or_higher("user", "admin") is False

    def test_moderator_has_user_role(self) -> None:
        """Test that moderator role satisfies user requirement."""
        assert has_role_or_higher("moderator", "user") is True

    def test_moderator_has_moderator_role(self) -> None:
        """Test that moderator role satisfies moderator requirement."""
        assert has_role_or_higher("moderator", "moderator") is True

    def test_moderator_does_not_have_admin(self) -> None:
        """Test that moderator role does not satisfy admin requirement."""
        assert has_role_or_higher("moderator", "admin") is False

    def test_admin_has_all_roles(self) -> None:
        """Test that admin role satisfies all requirements."""
        assert has_role_or_higher("admin", "user") is True
        assert has_role_or_higher("admin", "moderator") is True
        assert has_role_or_higher("admin", "admin") is True

    def test_unknown_role_treated_as_user(self) -> None:
        """Test that unknown roles are treated as lowest level."""
        assert has_role_or_higher("unknown", "user") is True
        assert has_role_or_higher("unknown", "moderator") is False


class TestUserRoleField:
    """Test cases for user role field."""

    def test_default_role_is_user(self, sample_user: UserDB) -> None:
        """Test that default role is 'user'."""
        assert sample_user.role == "user"

    def test_admin_user_has_admin_role(self, admin_user: UserDB) -> None:
        """Test that admin user has 'admin' role."""
        assert admin_user.role == "admin"

    def test_role_can_be_set(self) -> None:
        """Test that role can be set on user."""
        user = UserDB(
            uuid=uuid4(),
            username="moduser",
            email="mod@example.com",
            role="moderator",
        )

        assert user.role == "moderator"


class TestHasPermission:
    """Test permission resolution for different roles."""

    def test_regular_user_has_only_basic_blog_permissions(self) -> None:
        """Regular users should keep blog access but not admin access."""
        user = _make_user("user")

        assert has_permission(user, Permission.READ_BLOGS) is True
        assert has_permission(user, Permission.READ_ADMIN) is False

    def test_moderator_has_elevated_blog_permissions_but_not_admin(self) -> None:
        """Moderators should gain moderation powers without admin access."""
        moderator = _make_user("moderator")

        assert has_permission(moderator, Permission.DELETE_BLOGS) is True
        assert has_permission(moderator, Permission.READ_ADMIN) is False

    def test_unknown_role_has_no_permissions(self) -> None:
        """Unknown roles should not inherit permissions by accident."""
        unknown = _make_user("unknown")

        assert has_permission(unknown, Permission.READ_BLOGS) is False


class TestPermissionDependencies:
    """Test RBAC dependency factories directly."""

    @pytest.mark.asyncio
    async def test_require_role_allows_listed_role(self) -> None:
        """Allowed roles should pass through unchanged."""
        moderator = _make_user("moderator")
        role_checker = require_role(["moderator", "admin"])

        assert await role_checker(user=moderator) is moderator

    @pytest.mark.asyncio
    async def test_require_role_rejects_unlisted_role(self) -> None:
        """Unlisted roles should receive a 403 with helpful detail."""
        user = _make_user("user")
        role_checker = require_role(["admin"])

        with pytest.raises(HTTPException) as exc_info:
            await role_checker(user=user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Insufficient permissions. Required role: admin"

    @pytest.mark.asyncio
    async def test_require_role_or_higher_allows_admin(self) -> None:
        """Higher roles should satisfy lower minimum-role requirements."""
        admin = _make_user("admin")
        role_checker = require_role_or_higher("moderator")

        assert await role_checker(user=admin) is admin

    @pytest.mark.asyncio
    async def test_require_role_or_higher_rejects_lower_role(self) -> None:
        """Lower roles should be rejected by hierarchy-based requirements."""
        user = _make_user("user")
        role_checker = require_role_or_higher("moderator")

        with pytest.raises(HTTPException) as exc_info:
            await role_checker(user=user)

        assert exc_info.value.status_code == 403
        assert (
            exc_info.value.detail == "Insufficient permissions. Required role: moderator or higher"
        )

    @pytest.mark.asyncio
    async def test_require_permission_allows_admin_permission(self) -> None:
        """Users with the required permission should pass dependency checks."""
        admin = _make_user("admin")
        permission_checker = require_permission(Permission.READ_ADMIN)

        assert await permission_checker(user=admin) is admin

    @pytest.mark.asyncio
    async def test_require_permission_rejects_missing_permission(self) -> None:
        """Missing permissions should return the expected 403 detail."""
        moderator = _make_user("moderator")
        permission_checker = require_permission(Permission.READ_ADMIN)

        with pytest.raises(HTTPException) as exc_info:
            await permission_checker(user=moderator)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Insufficient permissions. Required: read:admin"
