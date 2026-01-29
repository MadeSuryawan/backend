# tests/services/conftest.py
"""Pytest fixtures for services tests."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from PIL import Image

from app.services.profile_picture import ProfilePictureService
from app.services.storage.base import StorageService


@pytest.fixture
def sample_user_id() -> str:
    """Generate a sample user ID."""
    return str(uuid4())


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    """Create valid JPEG image bytes."""
    img = Image.new("RGB", (200, 200), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def valid_png_bytes() -> bytes:
    """Create valid PNG image bytes."""
    img = Image.new("RGBA", (200, 200), color="blue")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def large_image_bytes() -> bytes:
    """Create a large image (>5MB) for testing size limits."""
    # Create a large image that exceeds 5MB
    img = Image.new("RGB", (4000, 4000), color="green")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def invalid_image_bytes() -> bytes:
    """Create invalid image bytes (not a real image)."""
    return b"not a valid image content"


@pytest.fixture
def mock_upload_file(valid_jpeg_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with valid JPEG content."""
    mock_file = MagicMock()
    mock_file.content_type = "image/jpeg"
    mock_file.filename = "test.jpg"
    mock_file.read = AsyncMock(return_value=valid_jpeg_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_png(valid_png_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with valid PNG content."""
    mock_file = MagicMock()
    mock_file.content_type = "image/png"
    mock_file.filename = "test.png"
    mock_file.read = AsyncMock(return_value=valid_png_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_large(large_image_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with large image content."""
    mock_file = MagicMock()
    mock_file.content_type = "image/png"
    mock_file.filename = "large.png"
    mock_file.read = AsyncMock(return_value=large_image_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_invalid(invalid_image_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with invalid image content."""
    mock_file = MagicMock()
    mock_file.content_type = "image/jpeg"
    mock_file.filename = "invalid.jpg"
    mock_file.read = AsyncMock(return_value=invalid_image_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_unsupported() -> MagicMock:
    """Create a mock UploadFile with unsupported content type."""
    mock_file = MagicMock()
    mock_file.content_type = "image/gif"
    mock_file.filename = "test.gif"
    mock_file.read = AsyncMock(return_value=b"GIF89a...")
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_storage_service() -> MagicMock:
    """Create a mock storage service."""
    mock = MagicMock(spec=StorageService)
    mock.upload_profile_picture = AsyncMock(return_value="https://example.com/pic.jpg")
    mock.delete_profile_picture = AsyncMock(return_value=True)
    mock.get_profile_picture_url = MagicMock(return_value="https://example.com/pic.jpg")
    return mock


@pytest.fixture
def profile_picture_service(mock_storage_service: MagicMock) -> ProfilePictureService:
    """Create a ProfilePictureService with mocked storage."""
    # Pass the mock storage directly to the service constructor
    return ProfilePictureService(storage=mock_storage_service)
