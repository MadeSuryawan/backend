"""Tests for profile picture API endpoints."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_cache_manager, get_current_user, get_user_repository
from app.errors.upload import ImageTooLargeError, UnsupportedImageTypeError
from app.main import app
from app.models import UserDB


@pytest.fixture
def override_dependencies(sample_user: UserDB) -> Generator[MagicMock]:
    """Override route dependencies with lightweight mocks."""
    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock(return_value=sample_user)
    mock_repo.update = AsyncMock(return_value=sample_user)

    mock_cache = MagicMock()
    mock_cache.delete = AsyncMock()

    app.state.cache_manager = mock_cache
    app.dependency_overrides[get_current_user] = lambda: sample_user
    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_cache_manager] = lambda: mock_cache

    yield mock_repo

    app.dependency_overrides.clear()
    if hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")


class TestUploadProfilePicture:
    """Tests for POST /{user_id}/profile-picture endpoint."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload requires authentication."""
        user_id = str(uuid4())
        response = await client.post(
            f"/users/{user_id}/profile-picture",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload fails with invalid UUID."""
        response = await client.post(
            "/users/invalid-uuid/profile-picture",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        # Should be 401 (unauthenticated) or 422 (validation error)
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_upload_success(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
        valid_jpeg_bytes: bytes,
    ) -> None:
        """Test successful profile picture upload."""
        picture_url = "https://cdn.example.com/profile.jpg"
        updated_user = sample_user.model_copy()
        updated_user.profile_picture = picture_url
        override_dependencies.update.return_value = updated_user

        with patch("app.routes.user._upload_pp", new_callable=AsyncMock) as mock_upload_pp:
            mock_upload_pp.return_value = picture_url

            response = await client.post(
                f"/users/{sample_user.uuid}/profile-picture",
                files={"file": ("test.jpg", valid_jpeg_bytes, "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["profilePicture"] == picture_url
        mock_upload_pp.assert_awaited_once()
        override_dependencies.update.assert_awaited_once_with(
            sample_user.uuid,
            {"profile_picture": picture_url},
        )

    @pytest.mark.asyncio
    async def test_upload_forbidden_for_other_user(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
        valid_jpeg_bytes: bytes,
    ) -> None:
        """Test upload is forbidden for a different non-admin user."""
        assert override_dependencies is not None
        with patch("app.routes.user._upload_pp", new_callable=AsyncMock) as mock_upload_pp:
            response = await client.post(
                f"/users/{uuid4()}/profile-picture",
                files={"file": ("test.jpg", valid_jpeg_bytes, "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 403
        mock_upload_pp.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_returns_not_found_when_repo_update_fails(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
        valid_jpeg_bytes: bytes,
    ) -> None:
        """Test upload returns 404 when repository update returns no user."""
        override_dependencies.update.return_value = None

        with patch("app.routes.user._upload_pp", new_callable=AsyncMock) as mock_upload_pp:
            mock_upload_pp.return_value = "https://cdn.example.com/profile.jpg"

            response = await client.post(
                f"/users/{sample_user.uuid}/profile-picture",
                files={"file": ("test.jpg", valid_jpeg_bytes, "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["detail"] == f"User with ID {sample_user.uuid} not found"

    @pytest.mark.asyncio
    async def test_upload_returns_unsupported_media_type_for_invalid_image_type(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
        valid_jpeg_bytes: bytes,
    ) -> None:
        """Test upload maps unsupported image type errors to HTTP 415."""
        mock_service = MagicMock()
        mock_service.upload_profile_picture = AsyncMock(
            side_effect=UnsupportedImageTypeError("image/gif"),
        )

        with patch("app.routes.user._get_pp_service", return_value=mock_service):
            response = await client.post(
                f"/users/{sample_user.uuid}/profile-picture",
                files={"file": ("test.jpg", valid_jpeg_bytes, "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 415
        assert response.json()["detail"] == (
            "This image format isn't supported. Please use JPEG, PNG, or WebP images."
        )
        override_dependencies.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_returns_request_entity_too_large_for_oversized_image(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
        valid_jpeg_bytes: bytes,
    ) -> None:
        """Test upload maps oversized image errors to HTTP 413."""
        mock_service = MagicMock()
        mock_service.upload_profile_picture = AsyncMock(side_effect=ImageTooLargeError())

        with patch("app.routes.user._get_pp_service", return_value=mock_service):
            response = await client.post(
                f"/users/{sample_user.uuid}/profile-picture",
                files={"file": ("test.jpg", valid_jpeg_bytes, "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 413
        assert response.json()["detail"] == (
            "Your image is too large. Please use an image smaller than 5MB."
        )
        override_dependencies.update.assert_not_awaited()


class TestDeleteProfilePicture:
    """Tests for DELETE /{user_id}/profile-picture endpoint."""

    @pytest.mark.asyncio
    async def test_delete_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that delete requires authentication."""
        user_id = str(uuid4())
        response = await client.delete(f"/users/{user_id}/profile-picture")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that delete fails with invalid UUID."""
        response = await client.delete("/users/invalid-uuid/profile-picture")
        # Should be 401 (unauthenticated) or 422 (validation error)
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_delete_success(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
    ) -> None:
        """Test successful profile picture deletion."""
        user_with_picture = sample_user.model_copy()
        user_with_picture.profile_picture = "https://cdn.example.com/profile.jpg"
        override_dependencies.get_by_id.return_value = user_with_picture

        mock_service = MagicMock()
        mock_service.delete_profile_picture = AsyncMock(return_value=True)

        with patch("app.routes.user._get_pp_service", return_value=mock_service):
            response = await client.delete(
                f"/users/{sample_user.uuid}/profile-picture",
                headers=auth_headers,
            )

        assert response.status_code == 204
        mock_service.delete_profile_picture.assert_awaited_once_with(str(sample_user.uuid))
        override_dependencies.update.assert_awaited_once_with(
            sample_user.uuid,
            {"profile_picture": None},
        )

    @pytest.mark.asyncio
    async def test_delete_forbidden_for_other_user(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
    ) -> None:
        """Test delete is forbidden for a different non-admin user."""
        assert override_dependencies is not None
        mock_service = MagicMock()
        mock_service.delete_profile_picture = AsyncMock(return_value=True)

        with patch("app.routes.user._get_pp_service", return_value=mock_service):
            response = await client.delete(
                f"/users/{uuid4()}/profile-picture",
                headers=auth_headers,
            )

        assert response.status_code == 403
        mock_service.delete_profile_picture.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_returns_bad_request_without_existing_picture(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
    ) -> None:
        """Test delete returns 400 when user has no profile picture."""
        assert override_dependencies is not None
        mock_service = MagicMock()
        mock_service.delete_profile_picture = AsyncMock(return_value=True)

        with patch("app.routes.user._get_pp_service", return_value=mock_service):
            response = await client.delete(
                f"/users/{sample_user.uuid}/profile-picture",
                headers=auth_headers,
            )

        assert response.status_code == 400
        assert response.json()["detail"] == "No profile picture to delete"
        mock_service.delete_profile_picture.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_returns_server_error_when_storage_delete_fails(
        self,
        client: AsyncClient,
        sample_user: UserDB,
        auth_headers: dict[str, str],
        override_dependencies: MagicMock,
    ) -> None:
        """Test delete returns 500 when storage deletion fails."""
        user_with_picture = sample_user.model_copy()
        user_with_picture.profile_picture = "https://cdn.example.com/profile.jpg"
        override_dependencies.get_by_id.return_value = user_with_picture

        mock_service = MagicMock()
        mock_service.delete_profile_picture = AsyncMock(return_value=False)

        with patch("app.routes.user._get_pp_service", return_value=mock_service):
            response = await client.delete(
                f"/users/{sample_user.uuid}/profile-picture",
                headers=auth_headers,
            )

        assert response.status_code == 500
        assert (
            response.json()["detail"] == "Failed to delete profile picture, Please try again later."
        )
        override_dependencies.update.assert_not_awaited()
