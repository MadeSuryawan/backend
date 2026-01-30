from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.errors.upload import (
    MediaLimitExceededError,
    UnsupportedImageTypeError,
    UnsupportedVideoTypeError,
)
from app.services.media import MediaService
from app.services.storage.base import StorageService


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (200, 200), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def storage() -> MagicMock:
    mock = MagicMock(spec=StorageService)
    mock.upload_media = AsyncMock(return_value="https://example.com/media")
    mock.delete_media = AsyncMock(return_value=True)
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
