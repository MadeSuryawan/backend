"""Tests for core user create, read, update, and delete routes."""

from collections.abc import Generator
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import (
    get_auth_service,
    get_current_user,
    get_user_repository,
)
from app.errors.database import DuplicateEntryError
from app.main import app
from app.models import UserDB
from app.utils.cache_keys import username_key


@pytest.fixture
def override_dependencies(sample_user: UserDB) -> Generator[tuple[MagicMock, MagicMock]]:
    """Override dependencies for user route tests."""
    mock_repo = MagicMock()
    mock_repo.create = AsyncMock(return_value=sample_user)
    mock_repo.get_all = AsyncMock(return_value=[sample_user])
    mock_repo.get_by_id = AsyncMock(return_value=sample_user)
    mock_repo.get_by_username = AsyncMock(return_value=sample_user)
    mock_repo.update = AsyncMock(return_value=sample_user)
    mock_repo.delete = AsyncMock(return_value=True)
    mock_repo.add_and_refresh = AsyncMock(return_value=sample_user)

    mock_auth_service = MagicMock()
    mock_auth_service.send_verification_email = AsyncMock()
    mock_auth_service.record_verification_sent = AsyncMock()

    app.state.cache_manager = MagicMock()
    app.state.cache_manager.get = AsyncMock(return_value=None)
    app.state.cache_manager.set = AsyncMock()
    app.state.cache_manager.delete = AsyncMock()
    app.state.cache_manager.clear = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: sample_user
    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    yield mock_repo, mock_auth_service

    app.dependency_overrides.clear()
    if hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")


@pytest.mark.asyncio
async def test_create_user_uses_detected_timezone_when_request_timezone_is_utc(
    client: AsyncClient,
    sample_user: UserDB,
    admin_user: UserDB,
    admin_auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    created_user = sample_user.model_copy(
        update={"username": "createduser", "email": "created@example.com"},
    )
    mock_repo.create.return_value = created_user
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with (
        patch(
            "app.routes.user.detect_timezone_by_ip",
            new_callable=AsyncMock,
        ) as mock_detect_timezone,
        patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate,
    ):
        mock_detect_timezone.return_value = "Asia/Makassar"
        response = await client.post(
            "/users/create",
            json={
                "userName": "createduser",
                "email": "created@example.com",
                "password": "Password123",
            },
            headers=admin_auth_headers,
        )

    assert response.status_code == 201
    assert response.json()["username"] == "createduser"
    mock_detect_timezone.assert_awaited_once()
    assert mock_repo.create.await_args.kwargs["timezone"] == "Asia/Makassar"
    mock_invalidate.assert_awaited_once_with(ANY, created_user.uuid, created_user.username)


@pytest.mark.asyncio
async def test_create_user_returns_conflict_for_duplicate_entry(
    client: AsyncClient,
    admin_user: UserDB,
    admin_auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    mock_repo.create.side_effect = DuplicateEntryError("Email already exists")
    app.dependency_overrides[get_current_user] = lambda: admin_user

    with (
        patch(
            "app.routes.user.detect_timezone_by_ip",
            new_callable=AsyncMock,
        ) as mock_detect_timezone,
        patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate,
    ):
        mock_detect_timezone.return_value = "UTC"
        response = await client.post(
            "/users/create",
            json={
                "userName": "createduser",
                "email": "taken@example.com",
                "password": "Password123",
            },
            headers=admin_auth_headers,
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already exists"
    mock_invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_users_returns_message_when_repository_is_empty(
    client: AsyncClient,
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    mock_repo.get_all.return_value = []

    response = await client.get("/users/all")

    assert response.status_code == 200
    assert response.json() == "No users found"
    mock_repo.get_all.assert_awaited_once_with(skip=0, limit=10)


@pytest.mark.asyncio
async def test_get_user_by_username_returns_not_found(
    client: AsyncClient,
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    mock_repo.get_by_username.return_value = None

    response = await client.get("/users/by-username/missing-user")

    assert response.status_code == 404
    assert response.json()["detail"] == "User with username 'missing-user' not found"


@pytest.mark.asyncio
async def test_update_user_invalidates_old_username_cache_when_username_changes(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    renamed_user = sample_user.model_copy(update={"username": "renamed-user"})
    mock_repo.update.return_value = renamed_user

    with patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate:
        response = await client.patch(
            f"/users/update/{sample_user.uuid}",
            json={"userName": "renamed-user"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["username"] == "renamed-user"
    assert (
        call(username_key(sample_user.username), namespace="users")
        in app.state.cache_manager.delete.await_args_list
    )
    mock_invalidate.assert_awaited_once_with(ANY, sample_user.uuid, renamed_user.username)


@pytest.mark.asyncio
async def test_update_user_returns_not_found_when_repo_update_fails(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    mock_repo.update.return_value = None

    with patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate:
        response = await client.patch(
            f"/users/update/{sample_user.uuid}",
            json={"bio": "Updated bio"},
            headers=auth_headers,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == f"User with ID {sample_user.uuid} not found"
    mock_invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_email_change_triggers_reverification(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, mock_auth_service = override_dependencies
    updated_user = sample_user.model_copy(update={"email": "newemail@example.com"})
    mock_repo.update.return_value = updated_user

    with patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate:
        response = await client.patch(
            f"/users/update/{sample_user.uuid}",
            json={"email": "newemail@example.com"},
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["email"] == "newemail@example.com"
    assert response.json()["isVerified"] is False
    mock_repo.add_and_refresh.assert_awaited_once_with(updated_user)
    mock_auth_service.send_verification_email.assert_awaited_once_with(updated_user)
    mock_auth_service.record_verification_sent.assert_awaited_once_with(sample_user.uuid)
    mock_invalidate.assert_awaited_once_with(ANY, sample_user.uuid, sample_user.username)


@pytest.mark.asyncio
async def test_update_user_returns_conflict_for_duplicate_email(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    mock_repo.update.side_effect = DuplicateEntryError("Email already exists")

    with patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate:
        response = await client.patch(
            f"/users/update/{sample_user.uuid}",
            json={"email": "taken@example.com"},
            headers=auth_headers,
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already exists"
    mock_invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_user_continues_when_profile_picture_cleanup_fails(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    user_with_picture = sample_user.model_copy(
        update={"profile_picture": "https://cdn.example.com/p.jpg"},
    )
    mock_repo.get_by_id.return_value = user_with_picture
    mock_service = MagicMock()
    mock_service.delete_profile_picture = AsyncMock(side_effect=RuntimeError("storage down"))

    with (
        patch("app.routes.user._get_pp_service", return_value=mock_service),
        patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate,
    ):
        response = await client.delete(
            f"/users/delete/{sample_user.uuid}",
            headers=auth_headers,
        )

    assert response.status_code == 204
    mock_service.delete_profile_picture.assert_awaited_once_with(str(sample_user.uuid))
    mock_repo.delete.assert_awaited_once_with(sample_user.uuid)
    mock_invalidate.assert_awaited_once_with(ANY, sample_user.uuid, sample_user.username)


@pytest.mark.asyncio
async def test_delete_user_returns_server_error_when_repo_delete_fails(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: tuple[MagicMock, MagicMock],
) -> None:
    mock_repo, _ = override_dependencies
    mock_repo.delete.return_value = False

    with (
        patch("app.routes.user._get_pp_service") as mock_get_pp_service,
        patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock) as mock_invalidate,
    ):
        response = await client.delete(
            f"/users/delete/{sample_user.uuid}",
            headers=auth_headers,
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to delete user, Please try again later."
    mock_get_pp_service.assert_not_called()
    mock_invalidate.assert_not_awaited()
