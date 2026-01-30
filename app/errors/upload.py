"""
Upload-related error classes.

This module defines custom exceptions for file upload operations,
including image validation and storage errors.
"""

from logging import getLogger

from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from app.errors.base import BaseAppError, create_exception_handler

logger = getLogger(__name__)


class UploadError(BaseAppError):
    """Base exception for upload-related errors."""

    def __init__(
        self,
        detail: str = "Upload failed",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(detail=detail, status_code=status_code)


class ImageTooLargeError(UploadError):
    """Exception raised when uploaded image exceeds size limit."""

    def __init__(
        self,
        max_size_mb: int = 5,
        actual_size_mb: float | None = None,
    ) -> None:
        detail = f"Image size exceeds maximum allowed size of {max_size_mb}MB"
        if actual_size_mb is not None:
            detail += f" (uploaded: {actual_size_mb:.2f}MB)"
        super().__init__(detail=detail, status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.max_size_mb = max_size_mb
        self.actual_size_mb = actual_size_mb


class UnsupportedImageTypeError(UploadError):
    """Exception raised when uploaded image type is not supported."""

    def __init__(
        self,
        content_type: str,
        allowed_types: list[str] | None = None,
    ) -> None:
        allowed = allowed_types or ["image/jpeg", "image/png", "image/webp"]
        detail = f"Unsupported image type: {content_type}. Allowed types: {', '.join(allowed)}"
        super().__init__(detail=detail, status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        self.content_type = content_type
        self.allowed_types = allowed


class InvalidImageError(UploadError):
    """Exception raised when uploaded file is not a valid image."""

    def __init__(self, detail: str = "Invalid or corrupted image file") -> None:
        super().__init__(detail=detail, status_code=HTTP_400_BAD_REQUEST)


class ImageProcessingError(UploadError):
    """Exception raised when image processing fails."""

    def __init__(self, detail: str = "Failed to process image") -> None:
        super().__init__(detail=detail, status_code=HTTP_500_INTERNAL_SERVER_ERROR)


class StorageError(UploadError):
    """Exception raised when storage operation fails."""

    def __init__(self, detail: str = "Storage operation failed") -> None:
        super().__init__(detail=detail, status_code=HTTP_500_INTERNAL_SERVER_ERROR)


class NoProfilePictureError(UploadError):
    """Exception raised when trying to delete non-existent profile picture."""

    def __init__(self) -> None:
        super().__init__(
            detail="No profile picture to delete",
            status_code=HTTP_400_BAD_REQUEST,
        )


class MediaLimitExceededError(UploadError):
    """Exception raised when media count limit is exceeded."""

    def __init__(
        self,
        media_type: str = "media",
        max_count: int = 5,
    ) -> None:
        detail = f"Maximum {media_type} limit of {max_count} exceeded"
        super().__init__(detail=detail, status_code=HTTP_400_BAD_REQUEST)
        self.media_type = media_type
        self.max_count = max_count


class VideoTooLargeError(UploadError):
    """Exception raised when uploaded video exceeds size limit."""

    def __init__(
        self,
        max_size_mb: int = 50,
        actual_size_mb: float | None = None,
    ) -> None:
        detail = f"Video size exceeds maximum allowed size of {max_size_mb}MB"
        if actual_size_mb is not None:
            detail += f" (uploaded: {actual_size_mb:.2f}MB)"
        super().__init__(detail=detail, status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        self.max_size_mb = max_size_mb
        self.actual_size_mb = actual_size_mb


class UnsupportedVideoTypeError(UploadError):
    """Exception raised when uploaded video type is not supported."""

    def __init__(
        self,
        content_type: str,
        allowed_types: list[str] | None = None,
    ) -> None:
        allowed = allowed_types or ["video/mp4", "video/webm", "video/quicktime"]
        detail = f"Unsupported video type: {content_type}. Allowed types: {', '.join(allowed)}"
        super().__init__(detail=detail, status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        self.content_type = content_type
        self.allowed_types = allowed


# Create exception handler for upload errors
upload_exception_handler = create_exception_handler(logger)
