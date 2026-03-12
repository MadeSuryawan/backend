"""Focused admin route coverage for auth, pagination, and admin safeguards."""

from collections.abc import AsyncGenerator, Generator
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from httpx import AsyncClient
from pydantic import ValidationError
from pytest import fixture, mark, raises

from app.db import get_session
from app.dependencies.dependencies import get_current_user, get_user_repository
from app.main import app
from app.models import UserDB
from app.routes.admin import (
    _validate_admin_response,
    update_user_role,
    update_user_verification_status,
)
from app.schemas.admin import AdminUserResponse, UserRoleUpdate, UserVerificationUpdate


@fixture
def override_admin_route_dependencies() -> Generator[tuple[MagicMock, MagicMock]]:
    """Override repository and session dependencies for admin route tests."""
    original_overrides = app.dependency_overrides.copy()

    mock_repo = MagicMock()
    mock_repo.get_all = AsyncMock(return_value=[])
    mock_repo.get_by_id = AsyncMock(return_value=None)

    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def override_session() -> AsyncGenerator[MagicMock]:
        yield mock_session

    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_session] = override_session

    yield mock_repo, mock_session

    app.dependency_overrides = original_overrides


@mark.asyncio
async def test_list_all_users_forbidden_for_non_admin(
    client: AsyncClient,
    sample_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Regular users should be blocked by the admin dependency."""
    mock_repo, mock_session = override_admin_route_dependencies
    app.dependency_overrides[get_current_user] = lambda: sample_user

    response = await client.get("/admin/users")

    assert response.status_code == 403
    assert "admin users only" in response.json()["detail"]
    mock_repo.get_all.assert_not_awaited()
    mock_session.execute.assert_not_awaited()


@mark.asyncio
async def test_list_all_users_returns_paginated_response_for_admin(
    client: AsyncClient,
    sample_user: UserDB,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Admins should receive the paginated user list and total count."""
    mock_repo, mock_session = override_admin_route_dependencies
    second_user = sample_user.model_copy(
        update={
            "uuid": uuid4(),
            "username": "seconduser",
            "email": "second@example.com",
        },
    )
    mock_repo.get_all.return_value = [sample_user, second_user]
    mock_session.execute.return_value.scalar_one.return_value = 2
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.get("/admin/users?skip=1&limit=2")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["skip"] == 1
    assert data["limit"] == 2
    assert [user["username"] for user in data["users"]] == ["testuser", "seconduser"]
    mock_repo.get_all.assert_awaited_once_with(skip=1, limit=2)
    mock_session.execute.assert_awaited_once()


@mark.asyncio
async def test_get_user_details_returns_404_for_missing_user(
    client: AsyncClient,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Admin detail endpoint should surface a missing-user 404 cleanly."""
    mock_repo, _ = override_admin_route_dependencies
    target_user_id = uuid4()
    mock_repo.get_by_id.return_value = None
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.get(f"/admin/users/{target_user_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
    mock_repo.get_by_id.assert_awaited_once_with(target_user_id)


@mark.asyncio
async def test_get_user_details_returns_user_payload_for_admin(
    client: AsyncClient,
    sample_user: UserDB,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Admin detail endpoint should return the serialized user payload."""
    mock_repo, _ = override_admin_route_dependencies
    mock_repo.get_by_id.return_value = sample_user
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.get(f"/admin/users/{sample_user.uuid}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(sample_user.uuid)
    assert data["username"] == sample_user.username
    assert data["role"] == sample_user.role
    assert data["is_verified"] is sample_user.is_verified
    mock_repo.get_by_id.assert_awaited_once_with(sample_user.uuid)


@mark.asyncio
async def test_update_user_role_updates_user_and_commits(
    client: AsyncClient,
    sample_user: UserDB,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Admin role updates should persist and return the updated user."""
    mock_repo, mock_session = override_admin_route_dependencies
    target_user = sample_user.model_copy()
    mock_repo.get_by_id.return_value = target_user
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.put(
        f"/admin/users/{target_user.uuid}/role",
        json={"role": "moderator"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "moderator"
    assert target_user.role == "moderator"
    mock_repo.get_by_id.assert_awaited_once_with(target_user.uuid)
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once_with(target_user)


@mark.asyncio
async def test_update_user_role_returns_404_for_missing_user(
    client: AsyncClient,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Role updates should return 404 when the target user does not exist."""
    mock_repo, mock_session = override_admin_route_dependencies
    target_user_id = uuid4()
    mock_repo.get_by_id.return_value = None
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.put(
        f"/admin/users/{target_user_id}/role",
        json={"role": "moderator"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
    mock_session.commit.assert_not_awaited()
    mock_session.refresh.assert_not_awaited()


@mark.asyncio
async def test_update_user_verification_updates_user_and_commits(
    client: AsyncClient,
    sample_user: UserDB,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Admin verification updates should persist and return the updated user."""
    mock_repo, mock_session = override_admin_route_dependencies
    target_user = sample_user.model_copy(update={"is_verified": False})
    mock_repo.get_by_id.return_value = target_user
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.put(
        f"/admin/users/{target_user.uuid}/verification",
        json={"status": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_verified"] is True
    assert target_user.is_verified is True
    mock_repo.get_by_id.assert_awaited_once_with(target_user.uuid)
    mock_session.commit.assert_awaited_once()
    mock_session.refresh.assert_awaited_once_with(target_user)


@mark.asyncio
async def test_update_user_verification_returns_404_for_missing_user(
    client: AsyncClient,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Verification updates should return 404 when the target user is missing."""
    mock_repo, mock_session = override_admin_route_dependencies
    target_user_id = uuid4()
    mock_repo.get_by_id.return_value = None
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.put(
        f"/admin/users/{target_user_id}/verification",
        json={"status": False},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"
    mock_session.commit.assert_not_awaited()
    mock_session.refresh.assert_not_awaited()


@mark.asyncio
async def test_get_system_stats_returns_aggregated_counts(
    client: AsyncClient,
    sample_user: UserDB,
    admin_user: UserDB,
    override_admin_route_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    """Admin stats should aggregate totals, verification, and role counts."""
    mock_repo, mock_session = override_admin_route_dependencies
    moderator_user = sample_user.model_copy(
        update={
            "uuid": uuid4(),
            "username": "moderatoruser",
            "email": "moderator@example.com",
            "role": "moderator",
        },
    )
    unverified_user = sample_user.model_copy(
        update={
            "uuid": uuid4(),
            "username": "pendinguser",
            "email": "pending@example.com",
            "is_verified": False,
        },
    )
    mock_repo.get_all.return_value = [sample_user, moderator_user, admin_user, unverified_user]
    mock_session.execute.return_value.scalar_one.return_value = 4
    app.dependency_overrides[get_current_user] = lambda: admin_user

    response = await client.get("/admin/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total_users": 4,
        "verified_users": 3,
        "admin_users": 1,
        "moderator_users": 1,
    }
    mock_repo.get_all.assert_awaited_once_with(skip=0, limit=10000)
    mock_session.execute.assert_awaited_once()


def test_validate_admin_response_wraps_validation_error(sample_user: UserDB) -> None:
    """Admin response validation failures should be wrapped with context."""
    try:
        AdminUserResponse.model_validate({})
    except ValidationError as exc:
        validation_error = exc
    else:
        details = "Expected AdminUserResponse.model_validate({}) to fail"
        raise AssertionError(details)

    with patch(
        "app.routes.admin.AdminUserResponse.model_validate",
        side_effect=validation_error,
    ):
        try:
            _validate_admin_response(sample_user)
        except ValueError as exc:
            assert "Validation error converting user to AdminUserResponse model" in str(exc)
        else:
            details = "Expected ValueError when admin response validation fails"
            raise AssertionError(details)


@mark.asyncio
async def test_update_user_role_rejects_constructed_invalid_role(
    sample_user: UserDB,
    admin_user: UserDB,
) -> None:
    """Direct handler calls still defend against unsupported role values."""
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=sample_user)
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    with raises(HTTPException) as exc:
        await update_user_role(
            sample_user.uuid,
            UserRoleUpdate.model_construct(role="owner"),
            admin_user,
            mock_repo,
            mock_session,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid role. Must be one of: user, moderator, admin"
    mock_repo.get_by_id.assert_not_awaited()
    mock_session.commit.assert_not_awaited()
    mock_session.refresh.assert_not_awaited()


@mark.asyncio
async def test_update_user_verification_rejects_constructed_invalid_status(
    sample_user: UserDB,
    admin_user: UserDB,
) -> None:
    """Direct handler calls still defend against non-boolean verification states."""
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=sample_user)
    mock_session = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    invalid_status = cast(bool, "not-a-bool")
    with raises(HTTPException) as exc:
        await update_user_verification_status(
            sample_user.uuid,
            UserVerificationUpdate.model_construct(status=invalid_status),
            admin_user,
            mock_repo,
            mock_session,
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid status. Must be one of: true, false"
    mock_repo.get_by_id.assert_not_awaited()
    mock_session.commit.assert_not_awaited()
    mock_session.refresh.assert_not_awaited()
