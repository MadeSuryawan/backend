"""
Media upload service.

This module provides the main service for handling media uploads
(images and videos) for reviews and blogs.
"""

from io import BytesIO
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image

from app.configs.settings import settings
from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
    UnsupportedVideoTypeError,
    VideoTooLargeError,
)
from app.services.storage import StorageService, get_storage_service


class MediaService:
    """
    Service for managing media uploads for reviews and blogs.

    Handles image and video validation, processing, and storage operations.
    """

    def __init__(self, storage: StorageService | None = None) -> None:
        """
        Initialize the media service.

        Args:
            storage: Optional storage service instance. If not provided,
                    the default storage service will be used.
        """
        self.storage = storage or get_storage_service()

        # Image settings
        self.image_max_size_bytes = settings.MEDIA_IMAGE_MAX_SIZE_MB * 1024 * 1024
        self.image_allowed_types = settings.MEDIA_IMAGE_ALLOWED_TYPES
        self.image_max_count_review = settings.MEDIA_IMAGE_MAX_COUNT_REVIEW
        self.image_max_count_blog = settings.MEDIA_IMAGE_MAX_COUNT_BLOG

        # Video settings
        self.video_max_size_bytes = settings.MEDIA_VIDEO_MAX_SIZE_MB * 1024 * 1024
        self.video_allowed_types = settings.MEDIA_VIDEO_ALLOWED_TYPES
        self.video_max_count_blog = settings.MEDIA_VIDEO_MAX_COUNT_BLOG

    def _validate_image_type(self, content_type: str | None) -> None:
        """Validate image content type."""
        if not content_type or content_type not in self.image_allowed_types:
            raise UnsupportedImageTypeError(
                content_type=content_type or "unknown",
                allowed_types=self.image_allowed_types,
            )

    def _validate_video_type(self, content_type: str | None) -> None:
        """Validate video content type."""
        if not content_type or content_type not in self.video_allowed_types:
            raise UnsupportedVideoTypeError(
                content_type=content_type or "unknown",
                allowed_types=self.video_allowed_types,
            )

    def _validate_image_size(self, file_data: bytes) -> None:
        """Validate image file size."""
        actual_size = len(file_data)
        if actual_size > self.image_max_size_bytes:
            raise ImageTooLargeError(
                max_size_mb=settings.MEDIA_IMAGE_MAX_SIZE_MB,
                actual_size_mb=actual_size / (1024 * 1024),
            )

    def _validate_video_size(self, file_data: bytes) -> None:
        """Validate video file size."""
        actual_size = len(file_data)
        if actual_size > self.video_max_size_bytes:
            raise VideoTooLargeError(
                max_size_mb=settings.MEDIA_VIDEO_MAX_SIZE_MB,
                actual_size_mb=actual_size / (1024 * 1024),
            )

    def _validate_image_content(self, file_data: bytes) -> Image.Image:
        """Validate that the file is a valid image."""
        try:
            img = Image.open(BytesIO(file_data))
            img.verify()
            img = Image.open(BytesIO(file_data))
            return img
        except Exception as e:
            mssg = f"Invalid or corrupted image file: {e!s}"
            raise InvalidImageError(mssg) from e

    def _process_image(self, img: Image.Image) -> tuple[bytes, str]:
        """Process and optimize the image."""
        try:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=85, optimize=True)
            buffer.seek(0)
            return buffer.read(), "image/jpeg"
        except Exception as e:
            mssg = f"Failed to process image: {e!s}"
            raise ImageProcessingError(mssg) from e

    async def upload_review_image(
        self,
        review_id: str,
        file: UploadFile,
        current_count: int,
    ) -> str:
        """
        Upload an image for a review.

        Args:
            review_id: Review ID
            file: Uploaded file
            current_count: Current number of images on the review

        Returns:
            str: URL to the uploaded image
        """
        if current_count >= self.image_max_count_review:
            raise MediaLimitExceededError(
                media_type="image",
                max_count=self.image_max_count_review,
            )

        self._validate_image_type(file.content_type)
        file_data = await file.read()
        self._validate_image_size(file_data)
        img = self._validate_image_content(file_data)
        processed_data, content_type = self._process_image(img)

        media_id = str(uuid4())
        return await self.storage.upload_media(
            folder="review_images",
            entity_id=review_id,
            media_id=media_id,
            file_data=processed_data,
            content_type=content_type,
        )

    async def upload_blog_image(
        self,
        blog_id: str,
        file: UploadFile,
        current_count: int,
    ) -> str:
        """
        Upload an image for a blog.

        Args:
            blog_id: Blog ID
            file: Uploaded file
            current_count: Current number of images on the blog

        Returns:
            str: URL to the uploaded image
        """
        if current_count >= self.image_max_count_blog:
            raise MediaLimitExceededError(
                media_type="image",
                max_count=self.image_max_count_blog,
            )

        self._validate_image_type(file.content_type)
        file_data = await file.read()
        self._validate_image_size(file_data)
        img = self._validate_image_content(file_data)
        processed_data, content_type = self._process_image(img)

        media_id = str(uuid4())
        return await self.storage.upload_media(
            folder="blog_images",
            entity_id=blog_id,
            media_id=media_id,
            file_data=processed_data,
            content_type=content_type,
        )

    async def upload_blog_video(
        self,
        blog_id: str,
        file: UploadFile,
        current_count: int,
    ) -> str:
        """
        Upload a video for a blog.

        Args:
            blog_id: Blog ID
            file: Uploaded file
            current_count: Current number of videos on the blog

        Returns:
            str: URL to the uploaded video
        """
        if current_count >= self.video_max_count_blog:
            raise MediaLimitExceededError(
                media_type="video",
                max_count=self.video_max_count_blog,
            )

        self._validate_video_type(file.content_type)
        file_data = await file.read()
        self._validate_video_size(file_data)

        media_id = str(uuid4())
        return await self.storage.upload_media(
            folder="blog_videos",
            entity_id=blog_id,
            media_id=media_id,
            file_data=file_data,
            content_type=file.content_type or "video/mp4",
        )

    async def delete_media(
        self,
        folder: str,
        entity_id: str,
        media_id: str,
    ) -> bool:
        """
        Delete a media file.

        Args:
            folder: Storage folder
            entity_id: Entity ID
            media_id: Media ID

        Returns:
            bool: True if deletion was successful
        """
        return await self.storage.delete_media(folder, entity_id, media_id)
