"""
Cloudinary storage implementation.

This module provides a Cloudinary-based storage backend for production
use. Offers automatic image optimization, CDN delivery, and transformations.
"""

import asyncio
from functools import partial

import cloudinary
import cloudinary.api
import cloudinary.uploader

from app.configs.settings import settings


class CloudinaryStorage:
    """
    Cloudinary storage implementation.

    Stores files in Cloudinary with automatic optimization,
    CDN delivery, and smart cropping for profile pictures.
    """

    def __init__(self) -> None:
        """Initialize Cloudinary with configured credentials."""
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
            secure=True,
        )
        self.folder = "baliblissed/profile_pictures"

    def _get_public_id(self, user_id: str) -> str:
        """
        Get the Cloudinary public ID for a user's profile picture.

        Args:
            user_id: Unique identifier for the user

        Returns:
            str: Cloudinary public ID
        """
        return f"{self.folder}/{user_id}"

    async def upload_profile_picture(
        self,
        user_id: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload a profile picture to Cloudinary.

        Args:
            user_id: Unique identifier for the user
            file_data: Raw image bytes
            content_type: MIME type of the image

        Returns:
            str: Cloudinary URL to the uploaded image
        """
        public_id = self._get_public_id(user_id)

        # Run blocking Cloudinary upload in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                cloudinary.uploader.upload,
                file_data,
                public_id=public_id,
                overwrite=True,
                resource_type="image",
                transformation=[
                    {
                        "width": settings.PROFILE_PICTURE_MAX_DIMENSION,
                        "height": settings.PROFILE_PICTURE_MAX_DIMENSION,
                        "crop": "fill",
                        "gravity": "face",
                    },
                    {"quality": "auto:good", "fetch_format": "auto"},
                ],
            ),
        )

        return result["secure_url"]

    async def delete_profile_picture(self, user_id: str) -> bool:
        """
        Delete a user's profile picture from Cloudinary.

        Args:
            user_id: Unique identifier for the user

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        public_id = self._get_public_id(user_id)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(cloudinary.uploader.destroy, public_id),
        )

        return result.get("result") == "ok"

    async def get_profile_picture_url(self, user_id: str) -> str | None:
        """
        Get the URL for a user's profile picture from Cloudinary.

        Args:
            user_id: Unique identifier for the user

        Returns:
            str | None: URL to the profile picture, or None if not found
        """
        public_id = self._get_public_id(user_id)

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                partial(cloudinary.api.resource, public_id),
            )
            return result.get("secure_url")
        except cloudinary.exceptions.NotFound:
            return None

