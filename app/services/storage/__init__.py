"""
Storage services package.

This package provides storage backends for file uploads,
with support for local filesystem and Cloudinary.
"""

from app.configs.settings import settings
from app.services.storage.base import StorageService
from app.services.storage.cloudinary_storage import CloudinaryStorage
from app.services.storage.local import LocalStorage


def get_storage_service() -> StorageService:
    """
    Get the configured storage service.

    Returns the appropriate storage implementation based on
    the STORAGE_PROVIDER setting.

    Returns:
        StorageService: Configured storage service instance
    """
    if settings.STORAGE_PROVIDER == "cloudinary":
        return CloudinaryStorage()
    return LocalStorage()


__all__ = [
    "CloudinaryStorage",
    "LocalStorage",
    "StorageService",
    "get_storage_service",
]
