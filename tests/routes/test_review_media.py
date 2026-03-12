"""Tests for review media endpoints."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_current_user, get_review_repository
from app.errors.upload import UnsupportedImageTypeError
from app.main import app
from app.models import ReviewDB, UserDB


@pytest.fixture
def override_review_media_dependencies(sample_user: UserDB) -> Generator[MagicMock]:
    original_overrides = app.dependency_overrides.copy()

    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock()
    mock_repo.add_image = AsyncMock()
    mock_repo.remove_image_by_media_id = AsyncMock(return_value=True)

    app.dependency_overrides[get_review_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: sample_user

    yield mock_repo

    app.dependency_overrides = original_overrides


class TestUploadReviewImage:
    """Tests for POST /reviews/{review_id}/images."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient) -> None:
        review_id = str(uuid4())
        response = await client.post(
            f"/reviews/upload-images/{review_id}",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/reviews/upload-images/invalid-uuid",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_upload_success_adds_image_to_review(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        mock_review = MagicMock(spec=ReviewDB)
        mock_review.user_id = sample_user.uuid
        mock_review.images_url = []
        override_review_media_dependencies.get_by_id.return_value = mock_review

        with patch("app.routes.review.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.upload_review_image.return_value = (
                "media-1",
                "https://example.com/review.jpg",
            )
            mock_media_service.return_value = mock_instance

            response = await client.post(
                f"/reviews/upload-images/{review_id}",
                files={"file": ("test.jpg", b"jpeg-data", "image/jpeg")},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json() == {
            "mediaId": "media-1",
            "url": "https://example.com/review.jpg",
            "mediaType": "image",
        }
        override_review_media_dependencies.add_image.assert_called_once_with(
            review_id,
            "https://example.com/review.jpg",
        )
        kwargs = mock_instance.upload_review_image.call_args.kwargs
        assert kwargs["review_id"] == str(review_id)
        assert kwargs["current_count"] == 0

    @pytest.mark.asyncio
    async def test_upload_returns_not_found_when_review_missing(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        override_review_media_dependencies.get_by_id.return_value = None

        response = await client.post(
            f"/reviews/upload-images/{review_id}",
            files={"file": ("test.jpg", b"jpeg-data", "image/jpeg")},
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Review not found"
        override_review_media_dependencies.add_image.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_maps_media_errors_to_http_response(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        mock_review = MagicMock(spec=ReviewDB)
        mock_review.user_id = sample_user.uuid
        mock_review.images_url = []
        override_review_media_dependencies.get_by_id.return_value = mock_review

        with patch("app.routes.review.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.upload_review_image.side_effect = UnsupportedImageTypeError("image/gif")
            mock_media_service.return_value = mock_instance

            response = await client.post(
                f"/reviews/upload-images/{review_id}",
                files={"file": ("test.gif", b"gif-data", "image/gif")},
                headers=auth_headers,
            )

        assert response.status_code == 415
        assert response.json()["detail"] == (
            "This image format isn't supported. Please use JPEG, PNG, or WebP images."
        )
        override_review_media_dependencies.add_image.assert_not_called()


class TestDeleteReviewImage:
    """Tests for DELETE /reviews/{review_id}/images/{media_id}."""

    @pytest.mark.asyncio
    async def test_delete_requires_authentication(self, client: AsyncClient) -> None:
        review_id = str(uuid4())
        response = await client.delete(f"/reviews/delete-images/{review_id}/media-1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.delete("/reviews/delete-images/invalid-uuid/media-1")
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_delete_success_removes_image(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        media_id = "media-1"
        mock_review = MagicMock(spec=ReviewDB)
        mock_review.user_id = sample_user.uuid
        mock_review.images_url = [f"https://example.com/review_images/{review_id}/{media_id}.jpg"]
        override_review_media_dependencies.get_by_id.return_value = mock_review

        with patch("app.routes.review.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.delete_media.return_value = True
            mock_media_service.return_value = mock_instance

            response = await client.delete(
                f"/reviews/delete-images/{review_id}/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 204
        mock_instance.delete_media.assert_called_once_with(
            folder="review_images",
            entity_id=str(review_id),
            media_id=media_id,
        )
        override_review_media_dependencies.remove_image_by_media_id.assert_called_once_with(
            review_id,
            media_id,
        )

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_review_missing(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        override_review_media_dependencies.get_by_id.return_value = None

        response = await client.delete(
            f"/reviews/delete-images/{review_id}/media-1",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Review not found"
        override_review_media_dependencies.remove_image_by_media_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_media_not_attached(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        media_id = "missing-media"
        mock_review = MagicMock(spec=ReviewDB)
        mock_review.user_id = sample_user.uuid
        mock_review.images_url = [f"https://example.com/review_images/{review_id}/other-media.jpg"]
        override_review_media_dependencies.get_by_id.return_value = mock_review

        with patch("app.routes.review.MediaService") as mock_media_service:
            response = await client.delete(
                f"/reviews/delete-images/{review_id}/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Media not found"
        mock_media_service.assert_not_called()
        override_review_media_dependencies.remove_image_by_media_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_storage_delete_fails(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        media_id = "media-1"
        mock_review = MagicMock(spec=ReviewDB)
        mock_review.user_id = sample_user.uuid
        mock_review.images_url = [f"https://example.com/review_images/{review_id}/{media_id}.jpg"]
        override_review_media_dependencies.get_by_id.return_value = mock_review

        with patch("app.routes.review.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.delete_media.return_value = False
            mock_media_service.return_value = mock_instance

            response = await client.delete(
                f"/reviews/delete-images/{review_id}/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Media not found"
        override_review_media_dependencies.remove_image_by_media_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_repo_remove_fails(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_review_media_dependencies: MagicMock,
    ) -> None:
        review_id = uuid4()
        media_id = "media-1"
        mock_review = MagicMock(spec=ReviewDB)
        mock_review.user_id = sample_user.uuid
        mock_review.images_url = [f"https://example.com/review_images/{review_id}/{media_id}.jpg"]
        override_review_media_dependencies.get_by_id.return_value = mock_review
        override_review_media_dependencies.remove_image_by_media_id.return_value = False

        with patch("app.routes.review.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.delete_media.return_value = True
            mock_media_service.return_value = mock_instance

            response = await client.delete(
                f"/reviews/delete-images/{review_id}/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Media not found"
        override_review_media_dependencies.remove_image_by_media_id.assert_awaited_once_with(
            review_id,
            media_id,
        )
