from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_cache_manager, get_current_user, get_user_repository
from app.main import app
from app.models import UserDB


@pytest.fixture
def override_dependencies(sample_user: UserDB) -> Generator[MagicMock]:
    """Override dependencies for testing."""
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=sample_user)
    mock_repo.update = AsyncMock(return_value=sample_user)

    mock_cache = MagicMock()
    mock_cache.delete = AsyncMock()

    # Set on app state for direct calls in decorators/helpers
    app.state.cache_manager = mock_cache

    app.dependency_overrides[get_current_user] = lambda: sample_user
    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_cache_manager] = lambda: mock_cache

    yield mock_repo

    app.dependency_overrides.clear()
    # Clean up app state if needed, but for tests usually just setting it is fine
    # Some test environments might expect it to stay or be cleared
    if hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")


@pytest.mark.asyncio
async def test_update_testimonial_success(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: MagicMock,
) -> None:
    """Test successful testimonial update."""
    payload = {"testimonial": "Great service! Highly recommend."}
    user_id = sample_user.uuid

    # Mock update value to return updated user
    updated_user = sample_user.model_copy()
    updated_user.testimonial = payload["testimonial"]
    override_dependencies.update.return_value = updated_user

    response = await client.patch(
        f"/users/{user_id}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["testimonial"] == payload["testimonial"]


@pytest.mark.asyncio
async def test_update_testimonial_unauthorized(
    client: AsyncClient,
    sample_user: UserDB,
) -> None:
    """Test testimonial update without authentication."""
    # Temporarily clear override to test real 401 logic if needed,
    # but get_current_user itself will raise 401 if token missing.
    payload = {"testimonial": "Test testimonial"}

    response = await client.patch(
        f"/users/{sample_user.uuid}/testimonial",
        json=payload,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_testimonial_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    override_dependencies: MagicMock,
) -> None:
    """Test testimonial update for another user (non-admin)."""
    other_user_id = uuid4()
    payload = {"testimonial": "Test testimonial"}

    response = await client.patch(
        f"/users/{other_user_id}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    # Since we use check_owner_or_admin, it will be 403 because
    # current_user.uuid (sample_user) != other_user_id.
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_testimonial_validation_error(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: MagicMock,
) -> None:
    """Test testimonial update with invalid data (too long)."""
    payload = {"testimonial": "x" * 501}  # Exceeds 500 char limit

    response = await client.patch(
        f"/users/{sample_user.uuid}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_testimonial_clear(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: MagicMock,
) -> None:
    """Test clearing testimonial by setting to None."""
    payload = {"testimonial": None}

    updated_user = sample_user.model_copy()
    updated_user.testimonial = None
    override_dependencies.update.return_value = updated_user

    response = await client.patch(
        f"/users/{sample_user.uuid}/testimonial",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["testimonial"] is None


@pytest.mark.asyncio
async def test_delete_testimonial_success(
    client: AsyncClient,
    sample_user: UserDB,
    auth_headers: dict[str, str],
    override_dependencies: MagicMock,
) -> None:
    """Test successful testimonial deletion."""
    override_dependencies.update.return_value = sample_user

    response = await client.delete(
        f"/users/{sample_user.uuid}/testimonial",
        headers=auth_headers,
    )

    assert response.status_code == 204
    override_dependencies.update.assert_called_once_with(sample_user.uuid, {"testimonial": None})


@pytest.mark.asyncio
async def test_delete_testimonial_unauthorized(
    client: AsyncClient,
    sample_user: UserDB,
) -> None:
    """Test testimonial deletion without authentication."""
    response = await client.delete(f"/users/{sample_user.uuid}/testimonial")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_testimonial_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    override_dependencies: MagicMock,
) -> None:
    """Test testimonial deletion for another user."""
    other_user_id = uuid4()
    response = await client.delete(
        f"/users/{other_user_id}/testimonial",
        headers=auth_headers,
    )
    assert response.status_code == 403
