"""Tests for registration and verification workflow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_auth_service, get_current_user, get_user_repository
from app.main import app
from app.models import UserDB


@pytest.fixture(autouse=True)
def setup_app_state(mock_cache_manager: MagicMock) -> Generator:
    app.state.cache_manager = mock_cache_manager
    yield
    # del app.state.cache_manager # verify if we need to delete, safe to enable if needed


@pytest.mark.asyncio
async def test_register_user_triggers_verification(
    client: AsyncClient,
    mock_cache_manager: MagicMock,
) -> None:
    """Test that public registration triggers verification email."""
    # Mock Repo
    mock_repo = MagicMock()
    mock_repo.create = AsyncMock()
    mock_user = UserDB(uuid=uuid4(), username="newuser", email="new@example.com", is_verified=False)
    mock_repo.create.return_value = mock_user

    # Mock Auth Service
    mock_auth_service = MagicMock()
    mock_auth_service.send_verification_email = AsyncMock(return_value="token")
    mock_auth_service.record_verification_sent = AsyncMock()

    # Override dependencies
    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    payload = {
        "userName": "newuser",
        "email": "new@example.com",
        "password": "Password123",  # Meets uppercase requirement
        "firstName": "New",
        "lastName": "User",
    }

    try:
        response = await client.post("/auth/register", json=payload)

        assert response.status_code == 201, f"Response: {response.text}"
        mock_auth_service.send_verification_email.assert_called_once_with(mock_user)
        mock_auth_service.record_verification_sent.assert_called_once_with(mock_user.uuid)

    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_user_forbidden_for_public(
    client: AsyncClient,
    sample_user: UserDB,
    mock_cache_manager: MagicMock,
) -> None:
    """Test that /users/create is forbidden for regular users."""
    # Mock the current user dependency to return a regular user (not admin)
    app.dependency_overrides[get_current_user] = lambda: sample_user

    try:
        response = await client.post("/users/create", json={})
        # Should be 403 Forbidden for non-admin user
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_user_admin_success(
    client: AsyncClient,
    admin_auth_headers: dict[str, str],
    admin_user: UserDB,
) -> None:
    """Test that /users/create works for admins."""
    # Mock Repo
    mock_repo = MagicMock()
    mock_repo.create = AsyncMock()
    mock_user = UserDB(
        uuid=uuid4(),
        username="admincreated",
        email="created@example.com",
    )
    mock_repo.create.return_value = mock_user

    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: admin_user

    payload = {
        "userName": "admincreated",
        "email": "created@example.com",
        "password": "Password123",
        "firstName": "Created",
        "lastName": "User",
    }

    try:
        response = await client.post("/users/create", json=payload, headers=admin_auth_headers)
        assert response.status_code == 201, f"Response: {response.text}"
        mock_repo.create.assert_called_once()
    finally:
        app.dependency_overrides.clear()
