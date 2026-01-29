"""
Profile picture service.

This module provides the main service for handling profile picture
uploads, validation, processing, and default avatar generation.
"""

from io import BytesIO
from urllib.parse import quote

from fastapi import UploadFile
from PIL import Image

from app.configs.settings import settings
from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.services.storage import StorageService, get_storage_service


class ProfilePictureService:
    """
    Service for managing user profile pictures.

    Handles image validation, processing, storage operations,
    and default avatar generation using DiceBear.
    """

    def __init__(self, storage: StorageService | None = None) -> None:
        """
        Initialize the profile picture service.

        Args:
            storage: Optional storage service instance. If not provided,
                    the default storage service will be used.
        """
        self.storage = storage or get_storage_service()
        self.max_size_bytes = settings.PROFILE_PICTURE_MAX_SIZE_MB * 1024 * 1024
        self.max_dimension = settings.PROFILE_PICTURE_MAX_DIMENSION
        self.quality = settings.PROFILE_PICTURE_QUALITY
        self.allowed_types = settings.PROFILE_PICTURE_ALLOWED_TYPES

    def validate_content_type(self, content_type: str | None) -> None:
        """
        Validate the content type of the uploaded file.

        Args:
            content_type: MIME type of the uploaded file

        Raises:
            UnsupportedImageTypeError: If content type is not allowed
        """
        if not content_type or content_type not in self.allowed_types:
            raise UnsupportedImageTypeError(
                content_type=content_type or "unknown",
                allowed_types=self.allowed_types,
            )

    def validate_file_size(self, file_data: bytes) -> None:
        """
        Validate the size of the uploaded file.

        Args:
            file_data: Raw file bytes

        Raises:
            ImageTooLargeError: If file exceeds maximum size
        """
        actual_size = len(file_data)
        if actual_size > self.max_size_bytes:
            raise ImageTooLargeError(
                max_size_mb=settings.PROFILE_PICTURE_MAX_SIZE_MB,
                actual_size_mb=actual_size / (1024 * 1024),
            )

    def validate_image_content(self, file_data: bytes) -> Image.Image:
        """
        Validate that the file is a valid image.

        Args:
            file_data: Raw file bytes

        Returns:
            Image.Image: Validated PIL Image object

        Raises:
            InvalidImageError: If file is not a valid image
        """
        try:
            img = Image.open(BytesIO(file_data))
            img.verify()  # Verify image integrity
            # Re-open after verify (verify closes the file)
            img = Image.open(BytesIO(file_data))
            return img
        except Exception as e:
            mssg = f"Invalid or corrupted image file: {e!s}"
            raise InvalidImageError(mssg) from e

    def process_image(self, img: Image.Image) -> tuple[bytes, str]:
        """
        Process and optimize the image.

        Resizes to max dimensions, converts to RGB if needed,
        and optimizes quality.

        Args:
            img: PIL Image object

        Returns:
            tuple[bytes, str]: Processed image bytes and content type
        """
        try:
            # Convert RGBA to RGB if necessary (for JPEG output)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Resize if larger than max dimension
            if img.width > self.max_dimension or img.height > self.max_dimension:
                img.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)

            # Save to bytes
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=self.quality, optimize=True)
            buffer.seek(0)

            return buffer.read(), "image/jpeg"
        except Exception as e:
            mssg = f"Failed to process image: {e!s}"
            raise ImageProcessingError(mssg) from e

    async def upload_profile_picture(
        self,
        user_id: str,
        file: UploadFile,
    ) -> str:
        """
        Upload and process a profile picture for a user.

        Args:
            user_id: Unique identifier for the user
            file: Uploaded file from FastAPI

        Returns:
            str: URL to the uploaded profile picture

        Raises:
            UnsupportedImageTypeError: If file type is not allowed
            ImageTooLargeError: If file is too large
            InvalidImageError: If file is not a valid image
            ImageProcessingError: If processing fails
        """
        # Validate content type
        self.validate_content_type(file.content_type)

        # Read file data
        file_data = await file.read()

        # Validate file size
        self.validate_file_size(file_data)

        # Validate image content
        img = self.validate_image_content(file_data)

        # Process image
        processed_data, content_type = self.process_image(img)

        # Upload to storage
        return await self.storage.upload_profile_picture(user_id, processed_data, content_type)

    async def delete_profile_picture(self, user_id: str) -> bool:
        """
        Delete a user's profile picture.

        Args:
            user_id: Unique identifier for the user

        Returns:
            bool: True if deletion was successful
        """
        return await self.storage.delete_profile_picture(user_id)

    @staticmethod
    def get_default_avatar_url(user_id: str, username: str | None = None) -> str:
        """
        Generate a DiceBear avatar URL for users without profile pictures.

        Uses the "initials" style for a clean, professional look.
        Falls back to user_id if username is not provided.

        Args:
            user_id: Unique identifier for the user (used as seed)
            username: Optional username for initials

        Returns:
            str: DiceBear avatar URL
        """
        # Use username for seed if available, otherwise use user_id
        seed = username or user_id

        # URL encode the seed to handle special characters
        encoded_seed = quote(seed, safe="")

        # DiceBear API v9 with initials style
        # Using a consistent background color based on seed
        return (
            f"https://api.dicebear.com/9.x/initials/svg"
            f"?seed={encoded_seed}"
            f"&backgroundColor=0ea5e9,14b8a6,8b5cf6,f59e0b,ef4444"
            f"&backgroundType=gradientLinear"
            f"&fontWeight=500"
        )
