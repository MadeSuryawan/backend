# tests/services/test_storage.py
"""Tests for storage services."""

import tempfile
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.services.storage.local import LocalStorage


class TestLocalStorage:
    """Tests for LocalStorage service."""

    @pytest.fixture
    def temp_uploads_dir(self) -> Generator[Path]:
        """Create a temporary uploads directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def local_storage(self, temp_uploads_dir: Path) -> LocalStorage:
        """Create a LocalStorage instance with temp directory."""
        with patch("app.services.storage.local.settings") as mock_settings:
            mock_settings.UPLOADS_DIR = temp_uploads_dir
            storage = LocalStorage()
            # Override base_path to use temp directory
            storage.base_path = temp_uploads_dir / "profile_pictures"
            storage.base_path.mkdir(parents=True, exist_ok=True)
            return storage

    @pytest.fixture
    def sample_image_bytes(self) -> bytes:
        """Create sample image bytes."""
        img = Image.new("RGB", (100, 100), color="red")
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        return buffer.getvalue()

    @pytest.mark.asyncio
    async def test_upload_profile_picture_success(
        self,
        local_storage: LocalStorage,
        sample_image_bytes: bytes,
    ) -> None:
        """Test successful profile picture upload."""
        user_id = "test-user-123"
        content_type = "image/jpeg"

        url = await local_storage.upload_profile_picture(
            user_id=user_id,
            file_data=sample_image_bytes,
            content_type=content_type,
        )

        # Verify URL format
        assert url.startswith("/uploads/profile_pictures/")
        assert user_id in url
        assert url.endswith(".jpg")

        # Verify file was created
        expected_path = local_storage.base_path / f"{user_id}.jpg"
        assert expected_path.exists()

    @pytest.mark.asyncio
    async def test_upload_profile_picture_replaces_existing(
        self,
        local_storage: LocalStorage,
        sample_image_bytes: bytes,
    ) -> None:
        """Test that uploading replaces existing picture."""
        user_id = "replace-user"

        # Upload first picture
        await local_storage.upload_profile_picture(
            user_id=user_id,
            file_data=sample_image_bytes,
            content_type="image/jpeg",
        )

        # Upload second picture (should replace)
        new_img = Image.new("RGB", (100, 100), color="blue")
        buffer = BytesIO()
        new_img.save(buffer, format="PNG")
        new_bytes = buffer.getvalue()

        url = await local_storage.upload_profile_picture(
            user_id=user_id,
            file_data=new_bytes,
            content_type="image/png",
        )

        # Verify only new file exists
        assert url.endswith(".png")
        old_path = local_storage.base_path / f"{user_id}.jpg"
        new_path = local_storage.base_path / f"{user_id}.png"
        assert not old_path.exists()
        assert new_path.exists()

    @pytest.mark.asyncio
    async def test_delete_profile_picture_success(
        self,
        local_storage: LocalStorage,
        sample_image_bytes: bytes,
    ) -> None:
        """Test successful profile picture deletion."""
        user_id = "delete-user"

        # First upload a picture
        await local_storage.upload_profile_picture(
            user_id=user_id,
            file_data=sample_image_bytes,
            content_type="image/jpeg",
        )

        # Verify file exists
        file_path = local_storage.base_path / f"{user_id}.jpg"
        assert file_path.exists()

        # Delete the picture
        result = await local_storage.delete_profile_picture(user_id)

        assert result is True
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_profile_picture_not_found(
        self,
        local_storage: LocalStorage,
    ) -> None:
        """Test deletion when no picture exists."""
        result = await local_storage.delete_profile_picture("nonexistent-user")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_profile_picture_url(
        self,
        local_storage: LocalStorage,
        sample_image_bytes: bytes,
    ) -> None:
        """Test URL retrieval for existing picture."""
        user_id = "url-user"

        # First upload a picture
        await local_storage.upload_profile_picture(
            user_id=user_id,
            file_data=sample_image_bytes,
            content_type="image/jpeg",
        )

        url = await local_storage.get_profile_picture_url(user_id)

        assert url == f"/uploads/profile_pictures/{user_id}.jpg"

    @pytest.mark.asyncio
    async def test_get_profile_picture_url_not_found(
        self,
        local_storage: LocalStorage,
    ) -> None:
        """Test URL retrieval when no picture exists."""
        url = await local_storage.get_profile_picture_url("nonexistent-user")
        assert url is None

    @pytest.mark.asyncio
    async def test_upload_media_image_success(
        self,
        local_storage: LocalStorage,
        sample_image_bytes: bytes,
    ) -> None:
        """Test successful media image upload."""
        folder = "review_images"
        entity_id = "review-123"
        media_id = "media-abc"

        url = await local_storage.upload_media(
            folder=folder,
            entity_id=entity_id,
            media_id=media_id,
            file_data=sample_image_bytes,
            content_type="image/jpeg",
        )

        assert url == f"/uploads/{folder}/{entity_id}/{media_id}.jpg"
        expected_path = local_storage.base_path.parent / folder / entity_id / f"{media_id}.jpg"
        assert expected_path.exists()

    @pytest.mark.asyncio
    async def test_upload_media_video_success(
        self,
        local_storage: LocalStorage,
    ) -> None:
        """Test successful media video upload."""
        folder = "blog_videos"
        entity_id = "blog-123"
        media_id = "media-vid"
        video_bytes = b"0" * 1024

        url = await local_storage.upload_media(
            folder=folder,
            entity_id=entity_id,
            media_id=media_id,
            file_data=video_bytes,
            content_type="video/mp4",
        )

        assert url == f"/uploads/{folder}/{entity_id}/{media_id}.mp4"
        expected_path = local_storage.base_path.parent / folder / entity_id / f"{media_id}.mp4"
        assert expected_path.exists()

    @pytest.mark.asyncio
    async def test_delete_media_success(
        self,
        local_storage: LocalStorage,
        sample_image_bytes: bytes,
    ) -> None:
        """Test successful media deletion."""
        folder = "review_images"
        entity_id = "review-del"
        media_id = "media-del"

        await local_storage.upload_media(
            folder=folder,
            entity_id=entity_id,
            media_id=media_id,
            file_data=sample_image_bytes,
            content_type="image/jpeg",
        )

        deleted = await local_storage.delete_media(
            folder=folder,
            entity_id=entity_id,
            media_id=media_id,
        )

        assert deleted is True
        expected_path = local_storage.base_path.parent / folder / entity_id / f"{media_id}.jpg"
        assert not expected_path.exists()
