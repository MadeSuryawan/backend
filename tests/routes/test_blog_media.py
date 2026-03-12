"""Tests for blog media endpoints."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_blog_repository, get_current_user
from app.errors.upload import UnsupportedVideoTypeError
from app.main import app
from app.models import BlogDB, UserDB


@pytest.fixture
def override_blog_media_dependencies(sample_user: UserDB) -> Generator[MagicMock]:
    original_overrides = app.dependency_overrides.copy()

    mock_repo = MagicMock()
    mock_repo.get_by_id = AsyncMock()
    mock_repo.add_image = AsyncMock()
    mock_repo.add_video = AsyncMock()
    mock_repo.remove_image_by_media_id = AsyncMock(return_value=True)
    mock_repo.remove_video_by_media_id = AsyncMock(return_value=True)

    app.dependency_overrides[get_blog_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: sample_user

    yield mock_repo

    app.dependency_overrides = original_overrides


class TestUploadBlogImage:
    """Tests for POST /blogs/{blog_id}/images."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient) -> None:
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/blogs/invalid-uuid/images",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_upload_success_adds_image_to_blog(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = []
        mock_blog.videos_url = []
        override_blog_media_dependencies.get_by_id.return_value = mock_blog

        with patch("app.routes.blog.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.upload_blog_image.return_value = (
                "media-1",
                "https://example.com/blog.jpg",
            )
            mock_media_service.return_value = mock_instance

            response = await client.post(
                f"/blogs/{blog_id}/images",
                files={"file": ("test.png", b"png-data", "image/png")},
                headers=auth_headers,
            )

        assert response.status_code == 201
        assert response.json() == {
            "mediaId": "media-1",
            "url": "https://example.com/blog.jpg",
            "mediaType": "image",
        }
        override_blog_media_dependencies.add_image.assert_called_once_with(
            blog_id,
            "https://example.com/blog.jpg",
        )
        args = mock_instance.upload_blog_image.call_args.args
        assert args[0] == str(blog_id)
        assert args[2] == 0

    @pytest.mark.asyncio
    async def test_upload_uses_existing_image_count(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = [
            "https://example.com/blog_images/media-1.jpg",
            "https://example.com/blog_images/media-2.jpg",
        ]
        mock_blog.videos_url = []
        override_blog_media_dependencies.get_by_id.return_value = mock_blog

        with patch("app.routes.blog.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.upload_blog_image.return_value = (
                "media-3",
                "https://example.com/blog.jpg",
            )
            mock_media_service.return_value = mock_instance

            response = await client.post(
                f"/blogs/{blog_id}/images",
                files={"file": ("test.png", b"png-data", "image/png")},
                headers=auth_headers,
            )

        assert response.status_code == 201
        args = mock_instance.upload_blog_image.call_args.args
        assert args[0] == str(blog_id)
        assert args[2] == 2


class TestUploadBlogVideo:
    """Tests for POST /blogs/{blog_id}/videos."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient) -> None:
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            files={"file": ("test.mp4", b"fake", "video/mp4")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/blogs/invalid-uuid/videos",
            files={"file": ("test.mp4", b"fake", "video/mp4")},
        )
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_upload_maps_media_service_errors(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = []
        mock_blog.videos_url = []
        override_blog_media_dependencies.get_by_id.return_value = mock_blog

        with patch("app.routes.blog.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.upload_blog_video.side_effect = UnsupportedVideoTypeError("video/avi")
            mock_media_service.return_value = mock_instance

            response = await client.post(
                f"/blogs/{blog_id}/videos",
                files={"file": ("test.avi", b"avi-data", "video/avi")},
                headers=auth_headers,
            )

        assert response.status_code == 415
        assert "supported" in response.json()["detail"]
        override_blog_media_dependencies.add_video.assert_not_called()


class TestDeleteBlogMedia:
    """Tests for DELETE /blogs/{blog_id}/media/{media_id}."""

    @pytest.mark.asyncio
    async def test_delete_requires_authentication(self, client: AsyncClient) -> None:
        blog_id = str(uuid4())
        response = await client.delete(f"/blogs/{blog_id}/media/media-1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.delete("/blogs/invalid-uuid/media/media-1")
        assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_media_id_missing(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = ["https://example.com/blog_images/existing-image.jpg"]
        mock_blog.videos_url = ["https://example.com/blog_videos/existing-video.mp4"]
        override_blog_media_dependencies.get_by_id.return_value = mock_blog

        response = await client.delete(
            f"/blogs/{blog_id}/media/missing-media",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Media not found"
        override_blog_media_dependencies.remove_image_by_media_id.assert_not_called()
        override_blog_media_dependencies.remove_video_by_media_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_video_media_success(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        media_id = "video-1"
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = []
        mock_blog.videos_url = [f"https://example.com/blog_videos/{media_id}.mp4"]
        override_blog_media_dependencies.get_by_id.return_value = mock_blog

        with patch("app.routes.blog.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.delete_media.return_value = True
            mock_media_service.return_value = mock_instance

            response = await client.delete(
                f"/blogs/{blog_id}/media/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json() == {"status": "blog_videos deleted"}
        mock_instance.delete_media.assert_awaited_once_with(
            folder="blog_videos",
            entity_id=str(blog_id),
            media_id=media_id,
        )
        override_blog_media_dependencies.remove_video_by_media_id.assert_awaited_once_with(
            blog_id,
            media_id,
        )
        override_blog_media_dependencies.remove_image_by_media_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_storage_delete_fails(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        media_id = "image-1"
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = [f"https://example.com/blog_images/{media_id}.jpg"]
        mock_blog.videos_url = []
        override_blog_media_dependencies.get_by_id.return_value = mock_blog

        with patch("app.routes.blog.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.delete_media.return_value = False
            mock_media_service.return_value = mock_instance

            response = await client.delete(
                f"/blogs/{blog_id}/media/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Media not found"
        override_blog_media_dependencies.remove_image_by_media_id.assert_not_called()
        override_blog_media_dependencies.remove_video_by_media_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_returns_not_found_when_repo_cleanup_fails(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
        sample_user: UserDB,
        override_blog_media_dependencies: MagicMock,
    ) -> None:
        blog_id = uuid4()
        media_id = "image-2"
        mock_blog = MagicMock(spec=BlogDB)
        mock_blog.author_id = sample_user.uuid
        mock_blog.images_url = [f"https://example.com/blog_images/{media_id}.jpg"]
        mock_blog.videos_url = []
        override_blog_media_dependencies.get_by_id.return_value = mock_blog
        override_blog_media_dependencies.remove_image_by_media_id.return_value = False

        with patch("app.routes.blog.MediaService") as mock_media_service:
            mock_instance = AsyncMock()
            mock_instance.delete_media.return_value = True
            mock_media_service.return_value = mock_instance

            response = await client.delete(
                f"/blogs/{blog_id}/media/{media_id}",
                headers=auth_headers,
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Media not found"
        override_blog_media_dependencies.remove_image_by_media_id.assert_awaited_once_with(
            blog_id,
            media_id,
        )
