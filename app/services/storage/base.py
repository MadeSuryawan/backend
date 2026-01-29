"""
Base storage protocol for file storage operations.

This module defines the abstract interface for storage backends,
allowing for different implementations (local, cloudinary, S3, etc.).
"""

from abc import abstractmethod
from typing import Protocol


class StorageService(Protocol):
    """
    Protocol defining the interface for storage services.

    All storage implementations must implement these methods
    to ensure consistent behavior across different backends.
    """

    @abstractmethod
    async def upload_profile_picture(
        self,
        user_id: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload a profile picture for a user.

        Args:
            user_id: Unique identifier for the user
            file_data: Raw image bytes
            content_type: MIME type of the image

        Returns:
            str: URL or path to the uploaded image
        """
        ...

    @abstractmethod
    async def delete_profile_picture(self, user_id: str) -> bool:
        """
        Delete a user's profile picture.

        Args:
            user_id: Unique identifier for the user

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        ...

    @abstractmethod
    async def get_profile_picture_url(self, user_id: str) -> str | None:
        """
        Get the URL for a user's profile picture.

        Args:
            user_id: Unique identifier for the user

        Returns:
            str | None: URL to the profile picture, or None if not found
        """
        ...

