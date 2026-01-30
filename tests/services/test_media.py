# tests/services/test_media.py
"""Tests for MediaService."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from PIL import Image

from app.errors.upload import (
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
    UnsupportedVideoTypeError,
    VideoTooLargeError,
)
from app.services.media import MediaService


@pytest.fixture
def sample_review_id() -> str:
    """Generate a sample review ID."""
    return str(uuid4())


@pytest.fixture
def sample_blog_id() -> str:
    """Generate a sample blog ID."""
    return str(uuid4())


@pytest.fixture
def sample_media_id() -> str:
    """Generate a sample media ID."""
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
    img = Image.new("RGB", (4000, 4000), color="green")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def invalid_image_bytes() -> bytes:
    """Create invalid image bytes (not a real image)."""
    return b"not a valid image content"


@pytest.fixture
def valid_video_bytes() -> bytes:
    """Create valid video bytes (mock)."""
    return b"fake video content for testing"


@pytest.fixture
def large_video_bytes() -> bytes:
    """Create large video bytes (>50MB) for testing size limits."""
    return b"x" * (51 * 1024 * 1024)


@pytest.fixture
def mock_upload_file_image(valid_jpeg_bytes: bytes) -> MagicMock:
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
def mock_upload_file_large_image(large_image_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with large image content."""
    mock_file = MagicMock()
    mock_file.content_type = "image/png"
    mock_file.filename = "large.png"
    mock_file.read = AsyncMock(return_value=large_image_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_invalid_image(invalid_image_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with invalid image content."""
    mock_file = MagicMock()
    mock_file.content_type = "image/jpeg"
    mock_file.filename = "invalid.jpg"
    mock_file.read = AsyncMock(return_value=invalid_image_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_unsupported_image() -> MagicMock:
    """Create a mock UploadFile with unsupported image type."""
    mock_file = MagicMock()
    mock_file.content_type = "image/gif"
    mock_file.filename = "test.gif"
    mock_file.read = AsyncMock(return_value=b"GIF89a...")
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_video(valid_video_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with video content."""
    mock_file = MagicMock()
    mock_file.content_type = "video/mp4"
    mock_file.filename = "test.mp4"
    mock_file.read = AsyncMock(return_value=valid_video_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_large_video(large_video_bytes: bytes) -> MagicMock:
    """Create a mock UploadFile with large video content."""
    mock_file = MagicMock()
    mock_file.content_type = "video/mp4"
    mock_file.filename = "large.mp4"
    mock_file.read = AsyncMock(return_value=large_video_bytes)
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_upload_file_unsupported_video() -> MagicMock:
    """Create a mock UploadFile with unsupported video type."""
    mock_file = MagicMock()
    mock_file.content_type = "video/avi"
    mock_file.filename = "test.avi"
    mock_file.read = AsyncMock(return_value=b"fake avi content")
    mock_file.seek = AsyncMock()
    return mock_file


@pytest.fixture
def mock_storage_service() -> MagicMock:
    """Create a mock storage service."""
    mock = MagicMock()
    mock.upload_media = AsyncMock(return_value="https://example.com/media/test.jpg")
    mock.delete_media = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def media_service(mock_storage_service: MagicMock) -> MediaService:
    """Create a MediaService with mocked storage."""
    return MediaService(storage=mock_storage_service)


class TestMediaServiceImageValidation:
    """Tests for image validation methods."""

    def test_validate_image_type_valid_jpeg(self, media_service: MediaService) -> None:
        """Test validation passes for JPEG content type."""
        media_service._validate_image_type("image/jpeg")

    def test_validate_image_type_valid_png(self, media_service: MediaService) -> None:
        """Test validation passes for PNG content type."""
        media_service._validate_image_type("image/png")

    def test_validate_image_type_valid_webp(self, media_service: MediaService) -> None:
        """Test validation passes for WebP content type."""
        media_service._validate_image_type("image/webp")

    def test_validate_image_type_invalid(self, media_service: MediaService) -> None:
        """Test validation fails for unsupported content type."""
        with pytest.raises(UnsupportedImageTypeError) as exc_info:
            media_service._validate_image_type("image/gif")
        assert "Unsupported image type" in str(exc_info.value.detail)

    def test_validate_image_type_none(self, media_service: MediaService) -> None:
        """Test validation fails for None content type."""
        with pytest.raises(UnsupportedImageTypeError):
            media_service._validate_image_type(None)

    def test_validate_image_size_valid(self, media_service: MediaService) -> None:
        """Test validation passes for small file."""
        small_content = b"x" * 1024  # 1KB
        media_service._validate_image_size(small_content)

    def test_validate_image_size_too_large(self, media_service: MediaService) -> None:
        """Test validation fails for large file."""
        large_content = b"x" * (6 * 1024 * 1024)  # 6MB
        with pytest.raises(ImageTooLargeError) as exc_info:
            media_service._validate_image_size(large_content)
        assert "exceeds maximum" in str(exc_info.value.detail)


class TestMediaServiceVideoValidation:
    """Tests for video validation methods."""

    def test_validate_video_type_valid_mp4(self, media_service: MediaService) -> None:
        """Test validation passes for MP4 content type."""
        media_service._validate_video_type("video/mp4")

    def test_validate_video_type_valid_webm(self, media_service: MediaService) -> None:
        """Test validation passes for WebM content type."""
        media_service._validate_video_type("video/webm")

    def test_validate_video_type_valid_quicktime(self, media_service: MediaService) -> None:
        """Test validation passes for QuickTime content type."""
        media_service._validate_video_type("video/quicktime")

    def test_validate_video_type_invalid(self, media_service: MediaService) -> None:
        """Test validation fails for unsupported content type."""
        with pytest.raises(UnsupportedVideoTypeError) as exc_info:
            media_service._validate_video_type("video/avi")
        assert "Unsupported video type" in str(exc_info.value.detail)

    def test_validate_video_type_none(self, media_service: MediaService) -> None:
        """Test validation fails for None content type."""
        with pytest.raises(UnsupportedVideoTypeError):
            media_service._validate_video_type(None)

    def test_validate_video_size_valid(self, media_service: MediaService) -> None:
        """Test validation passes for small video file."""
        small_content = b"x" * (10 * 1024 * 1024)  # 10MB
        media_service._validate_video_size(small_content)

    def test_validate_video_size_too_large(self, media_service: MediaService) -> None:
        """Test validation fails for large video file."""
        large_content = b"x" * (51 * 1024 * 1024)  # 51MB
        with pytest.raises(VideoTooLargeError) as exc_info:
            media_service._validate_video_size(large_content)
        assert "exceeds maximum" in str(exc_info.value.detail)


class TestMediaServiceImageContentValidation:
    """Tests for image content validation."""

    def test_validate_image_content_valid_jpeg(
        self, media_service: MediaService, valid_jpeg_bytes: bytes,
    ) -> None:
        """Test validation passes for valid JPEG."""
        result = media_service._validate_image_content(valid_jpeg_bytes)
        assert result is not None

    def test_validate_image_content_valid_png(
        self, media_service: MediaService, valid_png_bytes: bytes,
    ) -> None:
        """Test validation passes for valid PNG."""
        result = media_service._validate_image_content(valid_png_bytes)
        assert result is not None

    def test_validate_image_content_invalid(
        self, media_service: MediaService, invalid_image_bytes: bytes,
    ) -> None:
        """Test validation fails for invalid image data."""
        with pytest.raises(InvalidImageError) as exc_info:
            media_service._validate_image_content(invalid_image_bytes)
        assert "Invalid or corrupted" in str(exc_info.value.detail)


class TestMediaServiceImageProcessing:
    """Tests for image processing."""

    def test_process_image_converts_rgba_to_rgb(self, media_service: MediaService) -> None:
        """Test that RGBA images are converted to RGB."""
        img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 128))

        processed_bytes, content_type = media_service._process_image(img)

        result_img = Image.open(BytesIO(processed_bytes))
        assert result_img.mode == "RGB"
        assert content_type == "image/jpeg"

    def test_process_image_optimizes_jpeg(self, media_service: MediaService) -> None:
        """Test that images are optimized as JPEG."""
        img = Image.new("RGB", (500, 500), color="blue")

        processed_bytes, content_type = media_service._process_image(img)

        assert content_type == "image/jpeg"
        # Verify it's a valid JPEG
        result_img = Image.open(BytesIO(processed_bytes))
        assert result_img.format == "JPEG"


class TestMediaServiceUploadReviewImage:
    """Tests for review image upload."""

    @pytest.mark.asyncio
    async def test_upload_review_image_success(
        self,
        media_service: MediaService,
        mock_upload_file_image: MagicMock,
        sample_review_id: str,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test successful review image upload."""
        url = await media_service.upload_review_image(
            review_id=sample_review_id,
            file=mock_upload_file_image,
            current_count=0,
        )

        assert url is not None
        mock_storage_service.upload_media.assert_called_once()
        call_args = mock_storage_service.upload_media.call_args
        assert call_args.kwargs["folder"] == "review_images"
        assert call_args.kwargs["entity_id"] == sample_review_id

    @pytest.mark.asyncio
    async def test_upload_review_image_limit_exceeded(
        self,
        media_service: MediaService,
        mock_upload_file_image: MagicMock,
        sample_review_id: str,
    ) -> None:
        """Test upload fails when image limit exceeded."""
        with pytest.raises(MediaLimitExceededError) as exc_info:
            await media_service.upload_review_image(
                review_id=sample_review_id,
                file=mock_upload_file_image,
                current_count=5,  # Max is 5
            )
        assert "Maximum" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_upload_review_image_unsupported_type(
        self,
        media_service: MediaService,
        mock_upload_file_unsupported_image: MagicMock,
        sample_review_id: str,
    ) -> None:
        """Test upload fails for unsupported image type."""
        with pytest.raises(UnsupportedImageTypeError):
            await media_service.upload_review_image(
                review_id=sample_review_id,
                file=mock_upload_file_unsupported_image,
                current_count=0,
            )

    @pytest.mark.asyncio
    async def test_upload_review_image_invalid_content(
        self,
        media_service: MediaService,
        mock_upload_file_invalid_image: MagicMock,
        sample_review_id: str,
    ) -> None:
        """Test upload fails for invalid image content."""
        with pytest.raises(InvalidImageError):
            await media_service.upload_review_image(
                review_id=sample_review_id,
                file=mock_upload_file_invalid_image,
                current_count=0,
            )


class TestMediaServiceUploadBlogImage:
    """Tests for blog image upload."""

    @pytest.mark.asyncio
    async def test_upload_blog_image_success(
        self,
        media_service: MediaService,
        mock_upload_file_image: MagicMock,
        sample_blog_id: str,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test successful blog image upload."""
        url = await media_service.upload_blog_image(
            blog_id=sample_blog_id,
            file=mock_upload_file_image,
            current_count=0,
        )

        assert url is not None
        mock_storage_service.upload_media.assert_called_once()
        call_args = mock_storage_service.upload_media.call_args
        assert call_args.kwargs["folder"] == "blog_images"
        assert call_args.kwargs["entity_id"] == sample_blog_id

    @pytest.mark.asyncio
    async def test_upload_blog_image_limit_exceeded(
        self,
        media_service: MediaService,
        mock_upload_file_image: MagicMock,
        sample_blog_id: str,
    ) -> None:
        """Test upload fails when image limit exceeded."""
        with pytest.raises(MediaLimitExceededError) as exc_info:
            await media_service.upload_blog_image(
                blog_id=sample_blog_id,
                file=mock_upload_file_image,
                current_count=10,  # Max is 10
            )
        assert "Maximum" in str(exc_info.value.detail)


class TestMediaServiceUploadBlogVideo:
    """Tests for blog video upload."""

    @pytest.mark.asyncio
    async def test_upload_blog_video_success(
        self,
        media_service: MediaService,
        mock_upload_file_video: MagicMock,
        sample_blog_id: str,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test successful blog video upload."""
        url = await media_service.upload_blog_video(
            blog_id=sample_blog_id,
            file=mock_upload_file_video,
            current_count=0,
        )

        assert url is not None
        mock_storage_service.upload_media.assert_called_once()
        call_args = mock_storage_service.upload_media.call_args
        assert call_args.kwargs["folder"] == "blog_videos"
        assert call_args.kwargs["entity_id"] == sample_blog_id

    @pytest.mark.asyncio
    async def test_upload_blog_video_limit_exceeded(
        self,
        media_service: MediaService,
        mock_upload_file_video: MagicMock,
        sample_blog_id: str,
    ) -> None:
        """Test upload fails when video limit exceeded."""
        with pytest.raises(MediaLimitExceededError) as exc_info:
            await media_service.upload_blog_video(
                blog_id=sample_blog_id,
                file=mock_upload_file_video,
                current_count=3,  # Max is 3
            )
        assert "Maximum" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_upload_blog_video_unsupported_type(
        self,
        media_service: MediaService,
        mock_upload_file_unsupported_video: MagicMock,
        sample_blog_id: str,
    ) -> None:
        """Test upload fails for unsupported video type."""
        with pytest.raises(UnsupportedVideoTypeError):
            await media_service.upload_blog_video(
                blog_id=sample_blog_id,
                file=mock_upload_file_unsupported_video,
                current_count=0,
            )

    @pytest.mark.asyncio
    async def test_upload_blog_video_too_large(
        self,
        media_service: MediaService,
        mock_upload_file_large_video: MagicMock,
        sample_blog_id: str,
    ) -> None:
        """Test upload fails for large video file."""
        with pytest.raises(VideoTooLargeError):
            await media_service.upload_blog_video(
                blog_id=sample_blog_id,
                file=mock_upload_file_large_video,
                current_count=0,
            )


class TestMediaServiceDeleteMedia:
    """Tests for media deletion."""

    @pytest.mark.asyncio
    async def test_delete_media_success(
        self,
        media_service: MediaService,
        sample_review_id: str,
        sample_media_id: str,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test successful media deletion."""
        result = await media_service.delete_media(
            folder="review_images",
            entity_id=sample_review_id,
            media_id=sample_media_id,
        )

        assert result is True
        mock_storage_service.delete_media.assert_called_once_with(
            "review_images",
            sample_review_id,
            sample_media_id,
        )

    @pytest.mark.asyncio
    async def test_delete_media_blog_image(
        self,
        media_service: MediaService,
        sample_blog_id: str,
        sample_media_id: str,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test successful blog image deletion."""
        result = await media_service.delete_media(
            folder="blog_images",
            entity_id=sample_blog_id,
            media_id=sample_media_id,
        )

        assert result is True
        mock_storage_service.delete_media.assert_called_once_with(
            "blog_images",
            sample_blog_id,
            sample_media_id,
        )

    @pytest.mark.asyncio
    async def test_delete_media_blog_video(
        self,
        media_service: MediaService,
        sample_blog_id: str,
        sample_media_id: str,
        mock_storage_service: MagicMock,
    ) -> None:
        """Test successful blog video deletion."""
        result = await media_service.delete_media(
            folder="blog_videos",
            entity_id=sample_blog_id,
            media_id=sample_media_id,
        )

        assert result is True
        mock_storage_service.delete_media.assert_called_once_with(
            "blog_videos",
            sample_blog_id,
            sample_media_id,
        )
