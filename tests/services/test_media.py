from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
    UnsupportedVideoTypeError,
    VideoTooLargeError,
)
from app.media import StorageService
from app.services.media import MediaService


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (200, 200), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


def _png_bytes() -> bytes:
    img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 128))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def storage() -> MagicMock:
    mock = MagicMock(spec=StorageService)
    mock.upload_media = AsyncMock(return_value="https://example.com/media")
    mock.delete_media = AsyncMock(return_value=True)
    mock.delete_all_media = AsyncMock(return_value=True)
    return mock


@pytest.mark.asyncio
async def test_upload_review_image_returns_media_id_and_url(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=_jpeg_bytes())

    with patch("app.services.media.uuid4", return_value="fixed-media-id"):
        media_id, url = await service.upload_review_image(
            review_id="review-1",
            file=file,
            current_count=0,
        )

    assert media_id == "fixed-media-id"
    assert url == "https://example.com/media"
    storage.upload_media.assert_called_once()
    _, kwargs = storage.upload_media.call_args
    assert kwargs["folder"] == "review_images"
    assert kwargs["entity_id"] == "review-1"
    assert kwargs["media_id"] == "fixed-media-id"


@pytest.mark.asyncio
async def test_upload_blog_video_unsupported_type(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "video/avi"
    file.read = AsyncMock(return_value=b"0" * 1024)

    with pytest.raises(UnsupportedVideoTypeError):
        await service.upload_blog_video(
            blog_id="blog-1",
            file=file,
            current_count=0,
        )


@pytest.mark.asyncio
async def test_upload_blog_image_unsupported_type(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/gif"
    file.read = AsyncMock(return_value=b"GIF89a")

    with pytest.raises(UnsupportedImageTypeError):
        await service.upload_blog_image(
            blog_id="blog-1",
            file=file,
            current_count=0,
        )


@pytest.mark.asyncio
async def test_upload_blog_image_limit_exceeded(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=_jpeg_bytes())

    with pytest.raises(MediaLimitExceededError):
        await service.upload_blog_image(
            blog_id="blog-1",
            file=file,
            current_count=service.image_max_count_blog,
        )

    storage.upload_media.assert_not_called()


@pytest.mark.asyncio
async def test_upload_review_image_limit_exceeded(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=_jpeg_bytes())

    with pytest.raises(MediaLimitExceededError):
        await service.upload_review_image(
            review_id="review-1",
            file=file,
            current_count=service.image_max_count_review,
        )


@pytest.mark.asyncio
async def test_upload_review_image_invalid_image_content(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=b"not-a-real-image")

    with pytest.raises(InvalidImageError):
        await service.upload_review_image(
            review_id="review-1",
            file=file,
            current_count=0,
        )

    storage.upload_media.assert_not_called()


@pytest.mark.asyncio
async def test_upload_review_image_rejects_oversized_image(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    service.image_max_size_bytes = 10

    file = MagicMock()
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=b"x" * 11)

    with pytest.raises(ImageTooLargeError):
        await service.upload_review_image(
            review_id="review-1",
            file=file,
            current_count=0,
        )

    storage.upload_media.assert_not_called()


@pytest.mark.asyncio
async def test_upload_review_image_processing_failure(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/jpeg"
    file.read = AsyncMock(return_value=_jpeg_bytes())

    broken_image = MagicMock()
    broken_image.mode = "RGB"
    broken_image.save.side_effect = OSError("boom")

    with (
        patch.object(service, "_validate_image_content", return_value=broken_image),
        pytest.raises(ImageProcessingError),
    ):
        await service.upload_review_image(
            review_id="review-1",
            file=file,
            current_count=0,
        )

    storage.upload_media.assert_not_called()


@pytest.mark.asyncio
async def test_upload_blog_image_returns_media_id_and_url(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "image/png"
    file.read = AsyncMock(return_value=_png_bytes())

    with patch("app.services.media.uuid4", return_value="blog-image-id"):
        media_id, url = await service.upload_blog_image(
            blog_id="blog-1",
            file=file,
            current_count=0,
        )

    assert media_id == "blog-image-id"
    assert url == "https://example.com/media"
    _, kwargs = storage.upload_media.call_args
    assert kwargs["folder"] == "blog_images"
    assert kwargs["entity_id"] == "blog-1"
    assert kwargs["media_id"] == "blog-image-id"
    assert kwargs["content_type"] == "image/jpeg"
    assert kwargs["file_data"]


@pytest.mark.asyncio
async def test_upload_blog_video_returns_media_id_and_url(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "video/mp4"
    file.read = AsyncMock(return_value=b"video-bytes")

    with patch("app.services.media.uuid4", return_value="blog-video-id"):
        media_id, url = await service.upload_blog_video(
            blog_id="blog-1",
            file=file,
            current_count=0,
        )

    assert media_id == "blog-video-id"
    assert url == "https://example.com/media"
    _, kwargs = storage.upload_media.call_args
    assert kwargs["folder"] == "blog_videos"
    assert kwargs["entity_id"] == "blog-1"
    assert kwargs["media_id"] == "blog-video-id"
    assert kwargs["content_type"] == "video/mp4"
    assert kwargs["file_data"] == b"video-bytes"


@pytest.mark.asyncio
async def test_upload_blog_video_limit_exceeded(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    file = MagicMock()
    file.content_type = "video/mp4"
    file.read = AsyncMock(return_value=b"video-bytes")

    with pytest.raises(MediaLimitExceededError):
        await service.upload_blog_video(
            blog_id="blog-1",
            file=file,
            current_count=service.video_max_count_blog,
        )

    storage.upload_media.assert_not_called()


@pytest.mark.asyncio
async def test_upload_blog_video_rejects_oversized_video(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    service.video_max_size_bytes = 3

    file = MagicMock()
    file.content_type = "video/mp4"
    file.read = AsyncMock(return_value=b"1234")

    with pytest.raises(VideoTooLargeError):
        await service.upload_blog_video(
            blog_id="blog-1",
            file=file,
            current_count=0,
        )

    storage.upload_media.assert_not_called()


@pytest.mark.asyncio
async def test_delete_media_returns_storage_result(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    storage.delete_media.return_value = False

    deleted = await service.delete_media(
        folder="review_images",
        entity_id="review-1",
        media_id="media-1",
    )

    assert deleted is False
    storage.delete_media.assert_awaited_once_with("review_images", "review-1", "media-1")


@pytest.mark.asyncio
async def test_delete_all_media_returns_storage_result(storage: MagicMock) -> None:
    service = MediaService(storage=storage)
    storage.delete_all_media.return_value = False

    deleted = await service.delete_all_media(
        folder="blog_images",
        entity_id="blog-1",
    )

    assert deleted is False
    storage.delete_all_media.assert_awaited_once_with("blog_images", "blog-1")
