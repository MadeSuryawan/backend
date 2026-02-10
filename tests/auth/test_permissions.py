"""Tests for RBAC permissions and dependencies."""

from uuid import uuid4

from app.models import UserDB
from app.rabc import (
    ROLE_HIERARCHY,
    has_role_or_higher,
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
