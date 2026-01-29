# tests/errors/test_upload_errors.py
"""Tests for app/errors/upload.py module."""

from unittest.mock import MagicMock

import pytest
from fastapi.responses import ORJSONResponse

from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    NoProfilePictureError,
    StorageError,
    UnsupportedImageTypeError,
    UploadError,
    upload_exception_handler,
)


class TestUploadError:
    """Tests for base UploadError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = UploadError()
        assert error.detail == "Upload failed"
        assert error.status_code == 500  # Default is 500 (internal server error)

    def test_custom_values(self) -> None:
        """Test custom initialization values."""
        error = UploadError(detail="Custom upload error", status_code=422)
        assert error.detail == "Custom upload error"
        assert error.status_code == 422

    def test_str_representation(self) -> None:
        """Test string representation returns message."""
        error = UploadError(detail="Test upload error")
        assert str(error) == "Test upload error"


class TestImageTooLargeError:
    """Tests for ImageTooLargeError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = ImageTooLargeError()
        assert "exceeds maximum" in error.detail
        assert error.status_code == 413

    def test_custom_max_size(self) -> None:
        """Test custom max size in message."""
        error = ImageTooLargeError(max_size_mb=10)
        assert "10MB" in error.detail


class TestUnsupportedImageTypeError:
    """Tests for UnsupportedImageTypeError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = UnsupportedImageTypeError(content_type="image/gif")
        assert "Unsupported image type" in error.detail
        assert "image/gif" in error.detail
        assert error.status_code == 415

    def test_custom_allowed_types(self) -> None:
        """Test custom allowed types in message."""
        error = UnsupportedImageTypeError(
            content_type="image/bmp",
            allowed_types=["image/jpeg", "image/png"],
        )
        assert "image/jpeg" in error.detail
        assert "image/png" in error.detail
        assert "image/bmp" in error.detail


class TestInvalidImageError:
    """Tests for InvalidImageError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = InvalidImageError()
        assert "Invalid or corrupted" in error.detail
        assert error.status_code == 400

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = InvalidImageError(detail="Custom invalid image message")
        assert error.detail == "Custom invalid image message"


class TestImageProcessingError:
    """Tests for ImageProcessingError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = ImageProcessingError()
        assert "Failed to process" in error.detail
        assert error.status_code == 500

    def test_custom_message(self) -> None:
        """Test custom error message."""
        error = ImageProcessingError(detail="Processing failed: out of memory")
        assert error.detail == "Processing failed: out of memory"


class TestStorageError:
    """Tests for StorageError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = StorageError()
        assert "Storage operation failed" in error.detail
        assert error.status_code == 500


class TestNoProfilePictureError:
    """Tests for NoProfilePictureError exception."""

    def test_default_values(self) -> None:
        """Test default initialization values."""
        error = NoProfilePictureError()
        assert "No profile picture" in error.detail
        assert error.status_code == 400  # Bad request, not 404


class TestUploadExceptionHandler:
    """Tests for upload_exception_handler function."""

    @pytest.mark.asyncio
    async def test_handler_with_upload_error(self) -> None:
        """Test handler with UploadError exception."""
        request = MagicMock()
        request.client.host = "192.168.1.1"
        request.url.path = "/api/upload"

        error = UploadError(detail="Upload failed", status_code=400)
        response = await upload_exception_handler(request, error)

        assert response.status_code == 400
        assert isinstance(response, ORJSONResponse)

    @pytest.mark.asyncio
    async def test_handler_with_image_too_large(self) -> None:
        """Test handler with ImageTooLargeError exception."""
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.url.path = "/api/profile-picture"

        error = ImageTooLargeError(max_size_mb=5)
        response = await upload_exception_handler(request, error)

        assert response.status_code == 413
        assert isinstance(response, ORJSONResponse)
