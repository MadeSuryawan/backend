# tests/services/test_profile_picture.py
"""Tests for ProfilePictureService."""

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.errors.upload import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.services.profile_picture import ProfilePictureService


class TestProfilePictureServiceValidation:
    """Tests for ProfilePictureService validation methods."""

    def test_validate_content_type_valid_jpeg(self) -> None:
        """Test validation passes for JPEG content type."""
        service = ProfilePictureService()
        # Should not raise
        service.validate_content_type("image/jpeg")

    def test_validate_content_type_valid_png(self) -> None:
        """Test validation passes for PNG content type."""
        service = ProfilePictureService()
        service.validate_content_type("image/png")

    def test_validate_content_type_valid_webp(self) -> None:
        """Test validation passes for WebP content type."""
        service = ProfilePictureService()
        service.validate_content_type("image/webp")

    def test_validate_content_type_invalid(self) -> None:
        """Test validation fails for unsupported content type."""
        service = ProfilePictureService()
        with pytest.raises(UnsupportedImageTypeError) as exc_info:
            service.validate_content_type("image/gif")
        assert "Unsupported image type" in str(exc_info.value.detail)

    def test_validate_content_type_none(self) -> None:
        """Test validation fails for None content type."""
        service = ProfilePictureService()
        with pytest.raises(UnsupportedImageTypeError):
            service.validate_content_type(None)

    def test_validate_file_size_valid(self) -> None:
        """Test validation passes for small file."""
        service = ProfilePictureService()
        small_content = b"x" * 1024  # 1KB
        service.validate_file_size(small_content)

    def test_validate_file_size_too_large(self) -> None:
        """Test validation fails for large file."""
        service = ProfilePictureService()
        # Create content larger than 5MB
        large_content = b"x" * (6 * 1024 * 1024)
        with pytest.raises(ImageTooLargeError) as exc_info:
            service.validate_file_size(large_content)
        assert "exceeds maximum" in str(exc_info.value.detail)


class TestProfilePictureServiceImageValidation:
    """Tests for image content validation."""

    def test_validate_image_content_valid_jpeg(self, valid_jpeg_bytes: bytes) -> None:
        """Test validation passes for valid JPEG."""
        service = ProfilePictureService()
        service.validate_image_content(valid_jpeg_bytes)

    def test_validate_image_content_valid_png(self, valid_png_bytes: bytes) -> None:
        """Test validation passes for valid PNG."""
        service = ProfilePictureService()
        service.validate_image_content(valid_png_bytes)

    def test_validate_image_content_invalid(self, invalid_image_bytes: bytes) -> None:
        """Test validation fails for invalid image data."""
        service = ProfilePictureService()
        with pytest.raises(InvalidImageError) as exc_info:
            service.validate_image_content(invalid_image_bytes)
        assert "Invalid or corrupted" in str(exc_info.value.detail)


class TestProfilePictureServiceProcessing:
    """Tests for image processing."""

    def test_process_image_resizes_large_image(self) -> None:
        """Test that large images are resized."""
        service = ProfilePictureService()
        # Create a large image
        img = Image.new("RGB", (2000, 2000), color="red")

        processed_bytes, content_type = service.process_image(img)

        # Verify the processed image is smaller
        result_img = Image.open(BytesIO(processed_bytes))
        assert result_img.width <= 1024
        assert result_img.height <= 1024
        assert content_type == "image/jpeg"

    def test_process_image_converts_rgba_to_rgb(self) -> None:
        """Test that RGBA images are converted to RGB."""
        service = ProfilePictureService()
        # Create RGBA image
        img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 128))

        processed_bytes, content_type = service.process_image(img)

        # Verify the result is RGB (JPEG doesn't support alpha)
        result_img = Image.open(BytesIO(processed_bytes))
        assert result_img.mode == "RGB"
        assert content_type == "image/jpeg"

    def test_process_image_maintains_aspect_ratio(self) -> None:
        """Test that aspect ratio is maintained during resize."""
        service = ProfilePictureService()
        # Create a wide image
        img = Image.new("RGB", (2000, 1000), color="blue")

        processed_bytes, content_type = service.process_image(img)

        result_img = Image.open(BytesIO(processed_bytes))
        # Aspect ratio should be maintained (2:1)
        assert result_img.width == 1024
        assert result_img.height == 512


class TestProfilePictureServiceUpload:
    """Tests for upload functionality."""

    @pytest.mark.asyncio
    async def test_upload_profile_picture_unsupported_type(
        self,
        profile_picture_service: ProfilePictureService,
        mock_upload_file_unsupported: MagicMock,
        sample_user_id: str,
    ) -> None:
        """Test upload fails for unsupported image type."""
        with pytest.raises(UnsupportedImageTypeError):
            await profile_picture_service.upload_profile_picture(
                user_id=sample_user_id,
                file=mock_upload_file_unsupported,
            )

    @pytest.mark.asyncio
    async def test_upload_profile_picture_invalid_image(
        self,
        profile_picture_service: ProfilePictureService,
        mock_upload_file_invalid: MagicMock,
        sample_user_id: str,
    ) -> None:
        """Test upload fails for invalid image content."""
        with pytest.raises(InvalidImageError):
            await profile_picture_service.upload_profile_picture(
                user_id=sample_user_id,
                file=mock_upload_file_invalid,
            )


class TestProfilePictureServiceDelete:
    """Tests for delete functionality."""

    @pytest.mark.asyncio
    async def test_delete_profile_picture_success(
        self,
        profile_picture_service: ProfilePictureService,
        sample_user_id: str,
    ) -> None:
        """Test successful profile picture deletion."""
        result = await profile_picture_service.delete_profile_picture(sample_user_id)
        assert result is True
        profile_picture_service.storage.delete_profile_picture.assert_called_once_with(  # type: ignore[union-attr]
            sample_user_id,
        )


class TestProfilePictureServiceDefaultAvatar:
    """Tests for default avatar URL generation."""

    def test_get_default_avatar_url_format(self) -> None:
        """Test default avatar URL format."""
        user_id = "test-user-123"
        url = ProfilePictureService.get_default_avatar_url(user_id)

        assert "api.dicebear.com" in url
        assert "initials" in url  # Uses initials style
        assert user_id in url

    def test_get_default_avatar_url_unique_per_user(self) -> None:
        """Test that different users get different avatar URLs."""
        url1 = ProfilePictureService.get_default_avatar_url("user-1")
        url2 = ProfilePictureService.get_default_avatar_url("user-2")

        assert url1 != url2

    def test_get_default_avatar_url_consistent(self) -> None:
        """Test that same user always gets same avatar URL."""
        user_id = "consistent-user"
        url1 = ProfilePictureService.get_default_avatar_url(user_id)
        url2 = ProfilePictureService.get_default_avatar_url(user_id)

        assert url1 == url2

    def test_get_default_avatar_url_with_username(self) -> None:
        """Test that username is used as seed when provided."""
        user_id = "user-123"
        username = "johndoe"
        url = ProfilePictureService.get_default_avatar_url(user_id, username)

        assert username in url
        assert user_id not in url  # Username takes precedence
