"""
Local filesystem storage implementation.

This module provides a local storage backend for development
and testing purposes. Files are stored in the local filesystem.
"""

from pathlib import Path

import aiofiles

from app.configs.settings import settings


class LocalStorage:
    """
    Local filesystem storage implementation.

    Stores files in the local filesystem under the configured
    uploads directory. Suitable for development and testing.
    """

    def __init__(self) -> None:
        """Initialize local storage with configured paths."""
        self.uploads_dir = settings.UPLOADS_DIR
        self.base_path = self.uploads_dir / "profile_pictures"
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the upload directory exists."""
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, user_id: str, extension: str = "jpg") -> Path:
        """
        Get the file path for a user's profile picture.

        Args:
            user_id: Unique identifier for the user
            extension: File extension (default: jpg)

        Returns:
            Path: Full path to the profile picture file
        """
        return self.base_path / f"{user_id}.{extension}"

    def _get_extension_from_content_type(self, content_type: str) -> str:
        """
        Get file extension from content type.

        Args:
            content_type: MIME type of the image

        Returns:
            str: File extension
        """
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        return extensions.get(content_type, "jpg")

    async def upload_profile_picture(
        self,
        user_id: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload a profile picture to local filesystem.

        Args:
            user_id: Unique identifier for the user
            file_data: Raw image bytes
            content_type: MIME type of the image

        Returns:
            str: URL path to the uploaded image
        """
        # Delete existing profile picture if any
        await self.delete_profile_picture(user_id)

        extension = self._get_extension_from_content_type(content_type)
        file_path = self._get_file_path(user_id, extension)

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_data)

        # Return URL path for serving via static files
        return f"/uploads/profile_pictures/{user_id}.{extension}"

    async def delete_profile_picture(self, user_id: str) -> bool:
        """
        Delete a user's profile picture from local filesystem.

        Args:
            user_id: Unique identifier for the user

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        # Check for all possible extensions
        for ext in ["jpg", "png", "webp"]:
            file_path = self._get_file_path(user_id, ext)
            if file_path.exists():
                file_path.unlink()
                return True
        return False

    async def get_profile_picture_url(self, user_id: str) -> str | None:
        """
        Get the URL for a user's profile picture.

        Args:
            user_id: Unique identifier for the user

        Returns:
            str | None: URL to the profile picture, or None if not found
        """
        for ext in ["jpg", "png", "webp"]:
            file_path = self._get_file_path(user_id, ext)
            if file_path.exists():
                return f"/uploads/profile_pictures/{user_id}.{ext}"
        return None

    def _get_media_extension(self, content_type: str) -> str:
        """
        Get file extension from content type for media files.

        Args:
            content_type: MIME type of the file

        Returns:
            str: File extension
        """
        extensions = {
            # Images
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            # Videos
            "video/mp4": "mp4",
            "video/webm": "webm",
            "video/quicktime": "mov",
        }
        return extensions.get(content_type, "bin")

    async def upload_media(
        self,
        folder: str,
        entity_id: str,
        media_id: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload media (image or video) to local filesystem.

        Args:
            folder: Storage folder (e.g., "review_images", "blog_media")
            entity_id: ID of the entity (review or blog)
            media_id: Unique ID for the media file
            file_data: Raw file bytes
            content_type: MIME type of the file

        Returns:
            str: URL path to the uploaded media
        """
        # Create folder structure: uploads/{folder}/{entity_id}/
        media_dir = self.uploads_dir / folder / entity_id
        media_dir.mkdir(parents=True, exist_ok=True)

        extension = self._get_media_extension(content_type)
        file_path = media_dir / f"{media_id}.{extension}"

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_data)

        return f"/uploads/{folder}/{entity_id}/{media_id}.{extension}"

    async def delete_media(
        self,
        folder: str,
        entity_id: str,
        media_id: str,
    ) -> bool:
        """
        Delete a media file from local filesystem.

        Args:
            folder: Storage folder
            entity_id: ID of the entity
            media_id: ID of the media file

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        media_dir = self.uploads_dir / folder / entity_id

        # Check for all possible extensions
        for ext in ["jpg", "png", "webp", "mp4", "webm", "mov"]:
            file_path = media_dir / f"{media_id}.{ext}"
            if file_path.exists():
                file_path.unlink()
                return True
        return False
