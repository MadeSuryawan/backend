# User Profile Picture Implementation Plan

## Overview

This plan outlines the implementation of user profile picture functionality, ensuring seamless integration with both OAuth (Google/WeChat) and direct email authentication methods.

## Current State Analysis

### Database

- ✅ The `users` table already has a `profile_picture` column (VARCHAR 500) in the initial migration (`alembic/versions/20251215_0001_initial_schema.py:41`)
- ✅ The `UserDB` model (`app/models/user.py:77-81`) already defines the `profile_picture` field

### OAuth Integration

- ✅ `AuthService.get_or_create_oauth_user()` (`app/services/auth.py:293-336`) already extracts profile picture from OAuth providers via `user_info.get("picture")` and passes it to `UserCreate`
- ✅ Google OAuth returns `picture` field in user info which is properly mapped

### User Schemas

- ✅ `UserCreate` (`app/schemas/user.py:158-162`) has `profile_picture: HttpUrl | None`
- ✅ `UserUpdate` (`app/schemas/user.py:224-228`) has `profile_picture: HttpUrl | None`
- ✅ `UserResponse` (`app/schemas/user.py:281`) includes `profile_picture` in response

### Repository

- ✅ `UserRepository.create()` (`app/repositories/user.py:79`) handles profile picture URL
- ✅ `UserRepository.update()` (`app/repositories/user.py:143-144`) handles profile picture URL updates

### What's Missing

1. **File Upload Service**: No service exists to handle actual image file uploads
2. **File Storage Configuration**: No cloud storage (S3, Cloudinary, GCS) configured
3. **Dedicated Upload Endpoint**: No endpoint for users to upload profile pictures as files
4. **Image Validation**: No image format/size validation for uploads
5. **Default Avatar Support**: No system for generating or serving default avatars

---

## Proposed Implementation

### Phase 1: File Storage Configuration

#### 1.1 Add Storage Settings (`app/configs/settings.py`)

```python
# File Storage Configuration
STORAGE_PROVIDER: Literal["local", "s3", "cloudinary"] = "local"
STORAGE_LOCAL_PATH: Path = Path("uploads/profile_pictures")

# S3 Configuration (optional)
AWS_ACCESS_KEY_ID: str | None = None
AWS_SECRET_ACCESS_KEY: str | None = None
AWS_S3_BUCKET: str | None = None
AWS_S3_REGION: str = "ap-southeast-1"

# Cloudinary Configuration (optional)
CLOUDINARY_CLOUD_NAME: str | None = None
CLOUDINARY_API_KEY: str | None = None
CLOUDINARY_API_SECRET: str | None = None

# Upload Constraints
MAX_PROFILE_PICTURE_SIZE: int = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]
```

---

### Phase 2: Create File Storage Service

#### 2.1 Create Storage Service Interface (`app/services/storage/__init__.py`)

```python
"""Storage service module for file uploads."""

from app.services.storage.base import StorageProtocol
from app.services.storage.local import LocalStorage

__all__ = ["StorageProtocol", "LocalStorage"]
```

#### 2.2 Create Base Storage Protocol (`app/services/storage/base.py`)

```python
"""Base storage protocol defining the interface for all storage implementations."""

from typing import Protocol


class StorageProtocol(Protocol):
    """Protocol defining storage operations for file uploads."""
    
    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload file and return public URL.
        
        Args:
            file_data: Raw file bytes to upload.
            filename: Original filename.
            content_type: MIME type of the file.
            
        Returns:
            Public URL where the file can be accessed.
        """
        ...
    
    async def delete(self, file_url: str) -> bool:
        """
        Delete file by URL.
        
        Args:
            file_url: URL of the file to delete.
            
        Returns:
            True if deletion was successful.
        """
        ...
```

#### 2.3 Implement Local Storage (`app/services/storage/local.py`)

```python
"""Local filesystem storage implementation."""

from pathlib import Path
from uuid import uuid4

import aiofiles

from app.configs import settings


class LocalStorage:
    """Local filesystem storage for development and small deployments."""
    
    def __init__(self, base_path: Path | None = None) -> None:
        """
        Initialize local storage.
        
        Args:
            base_path: Base directory for file storage.
        """
        self.base_path = base_path or settings.STORAGE_LOCAL_PATH
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Upload file to local filesystem."""
        # Generate unique filename with UUID to prevent collisions
        ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid4()}{ext}"
        file_path = self.base_path / unique_filename
        
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_data)
        
        # Return relative URL for static file serving
        return f"/uploads/profile_pictures/{unique_filename}"
    
    async def delete(self, file_url: str) -> bool:
        """Delete file from local filesystem."""
        # Extract filename from URL
        filename = Path(file_url).name
        file_path = self.base_path / filename
        
        if file_path.exists():
            file_path.unlink()
            return True
        return False
```

#### 2.4 Implement S3 Storage (`app/services/storage/s3.py`) [Optional]

```python
"""AWS S3 storage implementation."""

from uuid import uuid4

import aioboto3

from app.configs import settings


class S3Storage:
    """AWS S3 storage for production deployments."""
    
    def __init__(self) -> None:
        """Initialize S3 storage with credentials from settings."""
        self.session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION,
        )
        self.bucket = settings.AWS_S3_BUCKET
    
    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Upload file to S3 bucket."""
        ext = filename.rsplit(".", 1)[-1].lower()
        key = f"profile_pictures/{uuid4()}.{ext}"
        
        async with self.session.client("s3") as s3:
            await s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=file_data,
                ContentType=content_type,
            )
        
        return f"https://{self.bucket}.s3.{settings.AWS_S3_REGION}.amazonaws.com/{key}"
    
    async def delete(self, file_url: str) -> bool:
        """Delete file from S3 bucket."""
        # Extract key from URL
        key = file_url.split(f"{self.bucket}.s3.")[1].split("/", 1)[1]
        
        async with self.session.client("s3") as s3:
            await s3.delete_object(Bucket=self.bucket, Key=key)
        return True
```

#### 2.5 Implement Cloudinary Storage (`app/services/storage/cloudinary.py`) [Optional]

```python
"""Cloudinary storage implementation with automatic image optimization."""

from uuid import uuid4

import cloudinary
import cloudinary.uploader

from app.configs import settings


class CloudinaryStorage:
    """Cloudinary storage for optimized image delivery."""
    
    def __init__(self) -> None:
        """Initialize Cloudinary with credentials from settings."""
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
        )
    
    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Upload file to Cloudinary with optimization."""
        public_id = f"profile_pictures/{uuid4()}"
        
        result = cloudinary.uploader.upload(
            file_data,
            public_id=public_id,
            folder="baliblissed",
            resource_type="image",
            transformation=[
                {"width": 512, "height": 512, "crop": "fill", "gravity": "face"},
                {"quality": "auto", "fetch_format": "auto"},
            ],
        )
        
        return result["secure_url"]
    
    async def delete(self, file_url: str) -> bool:
        """Delete file from Cloudinary."""
        # Extract public_id from URL
        public_id = file_url.split("/")[-1].rsplit(".", 1)[0]
        cloudinary.uploader.destroy(f"baliblissed/profile_pictures/{public_id}")
        return True
```

---

### Phase 3: Create Profile Picture Service

#### 3.1 Create Service (`app/services/profile_picture.py`)

```python
"""Profile picture service for handling user avatar uploads."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile

from app.configs import settings
from app.errors.upload import (
    FileSizeTooLargeError,
    InvalidFileTypeError,
    ProfilePictureUploadError,
)
from app.repositories import UserRepository
from app.services.storage.base import StorageProtocol


class ProfilePictureService:
    """Service for handling profile picture operations."""
    
    def __init__(
        self,
        storage: StorageProtocol,
        user_repo: UserRepository,
    ) -> None:
        """
        Initialize the profile picture service.
        
        Args:
            storage: Storage backend for file operations.
            user_repo: User repository for database operations.
        """
        self.storage = storage
        self.user_repo = user_repo
    
    def validate_image(self, file: UploadFile) -> None:
        """
        Validate image file format and size.
        
        Args:
            file: Uploaded file to validate.
            
        Raises:
            InvalidFileTypeError: If file type is not allowed.
            FileSizeTooLargeError: If file exceeds size limit.
        """
        # Validate content type
        if file.content_type not in settings.ALLOWED_IMAGE_TYPES:
            raise InvalidFileTypeError(
                allowed_types=settings.ALLOWED_IMAGE_TYPES,
                actual_type=file.content_type,
            )
        
        # Validate file size (if available)
        if file.size and file.size > settings.MAX_PROFILE_PICTURE_SIZE:
            raise FileSizeTooLargeError(
                max_size=settings.MAX_PROFILE_PICTURE_SIZE,
                actual_size=file.size,
            )
    
    async def upload_profile_picture(
        self,
        user_id: UUID,
        file: UploadFile,
    ) -> str:
        """
        Upload and set user profile picture.
        
        Args:
            user_id: UUID of the user.
            file: Uploaded image file.
            
        Returns:
            URL of the uploaded profile picture.
            
        Raises:
            ProfilePictureUploadError: If upload fails.
        """
        # Validate the image
        self.validate_image(file)
        
        # Read file data
        file_data = await file.read()
        
        # Additional size check after reading (for chunked uploads)
        if len(file_data) > settings.MAX_PROFILE_PICTURE_SIZE:
            raise FileSizeTooLargeError(
                max_size=settings.MAX_PROFILE_PICTURE_SIZE,
                actual_size=len(file_data),
            )
        
        # Get user to check for existing profile picture
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            msg = f"User with ID {user_id} not found"
            raise ProfilePictureUploadError(msg)
        
        # Delete old profile picture if exists and is a local/uploaded file
        old_picture = user.profile_picture
        if old_picture and old_picture.startswith("/uploads/"):
            await self.storage.delete(old_picture)
        
        # Upload new profile picture
        picture_url = await self.storage.upload(
            file_data=file_data,
            filename=file.filename or "profile.jpg",
            content_type=file.content_type or "image/jpeg",
        )
        
        # Update user record
        user.profile_picture = picture_url
        user.updated_at = datetime.now(tz=UTC).replace(second=0, microsecond=0)
        await self.user_repo._add_and_refresh(user)  # noqa: SLF001
        
        return picture_url
    
    async def delete_profile_picture(self, user_id: UUID) -> bool:
        """
        Remove user's profile picture.
        
        Args:
            user_id: UUID of the user.
            
        Returns:
            True if deletion was successful.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.profile_picture:
            return False
        
        # Only delete if it's an uploaded file (not OAuth provider URL)
        if user.profile_picture.startswith("/uploads/"):
            await self.storage.delete(user.profile_picture)
        
        # Clear the profile picture field
        user.profile_picture = None
        user.updated_at = datetime.now(tz=UTC).replace(second=0, microsecond=0)
        await self.user_repo._add_and_refresh(user)  # noqa: SLF001
        
        return True
```

---

### Phase 4: Create Upload Endpoint

#### 4.1 Add Upload Error Classes (`app/errors/upload.py`)

```python
"""Upload-specific error classes."""

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_413_REQUEST_ENTITY_TOO_LARGE


class InvalidFileTypeError(HTTPException):
    """Raised when file type is not allowed."""
    
    def __init__(self, allowed_types: list[str], actual_type: str | None) -> None:
        """Initialize with allowed and actual file types."""
        super().__init__(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type: {actual_type}. Allowed types: {', '.join(allowed_types)}",
        )


class FileSizeTooLargeError(HTTPException):
    """Raised when file exceeds maximum size."""
    
    def __init__(self, max_size: int, actual_size: int) -> None:
        """Initialize with max and actual sizes."""
        max_mb = max_size / (1024 * 1024)
        actual_mb = actual_size / (1024 * 1024)
        super().__init__(
            status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {actual_mb:.2f}MB. Maximum allowed: {max_mb:.2f}MB",
        )


class ProfilePictureUploadError(HTTPException):
    """Raised when profile picture upload fails."""
    
    def __init__(self, message: str) -> None:
        """Initialize with error message."""
        super().__init__(
            status_code=HTTP_400_BAD_REQUEST,
            detail=message,
        )
```

#### 4.2 Add Profile Picture Routes (`app/routes/user.py`)

Add these endpoints to the existing user routes:

```python
from fastapi import File, UploadFile

from app.services.profile_picture import ProfilePictureService


# Add dependency for ProfilePictureService
ProfilePictureServiceDep = Annotated[ProfilePictureService, Depends(get_profile_picture_service)]


@router.post(
    "/{user_id}/profile-picture",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Upload profile picture",
    description="Upload or update user profile picture. Max 5MB, accepts JPEG/PNG/WebP.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "profilePicture": "/uploads/profile_pictures/abc123.jpg",
                    },
                },
            },
        },
        400: {
            "description": "Invalid file type",
            "content": {
                "application/json": {
                    "example": {"detail": "Invalid file type: text/plain. Allowed: image/jpeg, image/png, image/webp"},
                },
            },
        },
        413: {
            "description": "File too large",
            "content": {
                "application/json": {
                    "example": {"detail": "File too large: 10.5MB. Maximum allowed: 5.0MB"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_upload_profile_picture",
)
@timed("/users/profile-picture/upload")
@limiter.limit("10/hour")
@cache_busting(
    key_builder=lambda user_id, **kw: [user_id_key(user_id), users_list_key(0, 10)],
    namespace="users",
)
async def upload_profile_picture(
    request: Request,
    response: Response,
    user_id: UUID,
    file: Annotated[UploadFile, File(description="Profile picture image file")],
    deps: Annotated[UserOpsDeps, Depends()],
    profile_service: ProfilePictureServiceDep,
) -> UserResponse:
    """
    Upload or update user's profile picture.
    
    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier.
    file : UploadFile
        Image file to upload.
    deps : UserOpsDeps
        Operation dependencies (repo + current_user).
    profile_service : ProfilePictureService
        Profile picture service.
        
    Returns
    -------
    UserResponse
        Updated user with new profile picture URL.
    """
    # Check if user is owner or admin
    check_owner_or_admin(user_id, deps.current_user, "profile picture")
    
    # Upload profile picture
    await profile_service.upload_profile_picture(user_id, file)
    
    # Get updated user
    db_user = await deps.repo.get_by_id(user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    
    # Invalidate cache
    await get_cache_manager(request).delete(
        user_id_key(user_id),
        username_key(db_user.username),
        users_list_key(0, 10),
        namespace="users",
    )
    
    return db_user_to_response(db_user)


@router.delete(
    "/{user_id}/profile-picture",
    response_class=ORJSONResponse,
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete profile picture",
    description="Remove user's profile picture.",
    responses={
        204: {"description": "Profile picture deleted"},
        404: {
            "description": "User not found or no profile picture",
            "content": {
                "application/json": {
                    "example": {"detail": "User with ID <uuid> not found"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_delete_profile_picture",
)
@timed("/users/profile-picture/delete")
@limiter.limit("10/hour")
@cache_busting(
    key_builder=lambda user_id, **kw: [user_id_key(user_id), users_list_key(0, 10)],
    namespace="users",
)
async def delete_profile_picture(
    request: Request,
    response: Response,
    user_id: UUID,
    deps: Annotated[UserOpsDeps, Depends()],
    profile_service: ProfilePictureServiceDep,
) -> None:
    """
    Delete user's profile picture.
    
    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier.
    deps : UserOpsDeps
        Operation dependencies (repo + current_user).
    profile_service : ProfilePictureService
        Profile picture service.
    """
    # Check if user is owner or admin
    check_owner_or_admin(user_id, deps.current_user, "profile picture")
    
    # Get user for cache invalidation
    db_user = await deps.repo.get_by_id(user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    
    # Delete profile picture
    deleted = await profile_service.delete_profile_picture(user_id)
    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="No profile picture to delete",
        )
    
    # Invalidate cache
    await get_cache_manager(request).delete(
        user_id_key(user_id),
        username_key(db_user.username),
        users_list_key(0, 10),
        namespace="users",
    )
```

---

### Phase 5: Image Processing (Optional Enhancement)

#### 5.1 Add Image Processing Utils (`app/utils/image_processing.py`)

```python
"""Image processing utilities for profile pictures."""

from io import BytesIO

from PIL import Image


def resize_image(
    image_data: bytes,
    max_size: tuple[int, int] = (512, 512),
    quality: int = 85,
) -> bytes:
    """
    Resize image to fit within max dimensions while maintaining aspect ratio.
    
    Args:
        image_data: Raw image bytes.
        max_size: Maximum width and height.
        quality: JPEG quality (1-100).
        
    Returns:
        Processed image bytes.
    """
    img = Image.open(BytesIO(image_data))
    
    # Convert to RGB if necessary (for PNG with transparency)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # Resize maintaining aspect ratio
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    # Save to bytes
    output = BytesIO()
    img.save(output, format="JPEG", quality=quality, optimize=True)
    output.seek(0)
    
    return output.read()


def create_thumbnail(
    image_data: bytes,
    size: tuple[int, int] = (128, 128),
) -> bytes:
    """
    Create a square thumbnail from image.
    
    Args:
        image_data: Raw image bytes.
        size: Thumbnail dimensions.
        
    Returns:
        Thumbnail image bytes.
    """
    img = Image.open(BytesIO(image_data))
    
    # Convert to RGB
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # Create square crop from center
    width, height = img.size
    min_dim = min(width, height)
    left = (width - min_dim) // 2
    top = (height - min_dim) // 2
    right = left + min_dim
    bottom = top + min_dim
    
    img = img.crop((left, top, right, bottom))
    img = img.resize(size, Image.Resampling.LANCZOS)
    
    output = BytesIO()
    img.save(output, format="JPEG", quality=90, optimize=True)
    output.seek(0)
    
    return output.read()


def validate_image_content(image_data: bytes) -> str | None:
    """
    Validate image content and return actual MIME type.
    
    Args:
        image_data: Raw image bytes.
        
    Returns:
        Actual MIME type or None if invalid.
    """
    try:
        img = Image.open(BytesIO(image_data))
        format_to_mime = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
        }
        return format_to_mime.get(img.format)
    except Exception:
        return None
```

---

### Phase 6: Update Dependencies

#### 6.1 Add New Dependencies

Run these commands:

```bash
# Required dependencies
uv add python-multipart  # For file uploads in FastAPI
uv add Pillow            # Image processing
uv add aiofiles          # Async file operations

# Optional (based on storage provider choice)
uv add aioboto3          # For S3 storage
uv add cloudinary        # For Cloudinary storage
```

---

### Phase 7: Static Files Configuration

#### 7.1 Configure Static Files in FastAPI (`app/main.py`)

Add static files mount for local storage:

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.configs import settings

# Create uploads directory if using local storage
if settings.STORAGE_PROVIDER == "local":
    uploads_dir = Path("uploads/profile_pictures")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    # Mount static files for serving uploaded images
    app.mount(
        "/uploads",
        StaticFiles(directory="uploads"),
        name="uploads",
    )
```

---

### Phase 8: Testing

#### 8.1 Unit Tests (`tests/services/test_profile_picture.py`)

```python
"""Tests for profile picture service."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from PIL import Image

from app.errors.upload import FileSizeTooLargeError, InvalidFileTypeError
from app.services.profile_picture import ProfilePictureService


def create_test_image(format: str = "JPEG", size: tuple[int, int] = (100, 100)) -> bytes:
    """Create a test image in memory."""
    img = Image.new("RGB", size, color="red")
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Create mock storage backend."""
    storage = AsyncMock()
    storage.upload.return_value = "/uploads/profile_pictures/test.jpg"
    storage.delete.return_value = True
    return storage


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    """Create mock user repository."""
    repo = AsyncMock()
    user = MagicMock()
    user.profile_picture = None
    repo.get_by_id.return_value = user
    return repo


@pytest.fixture
def profile_service(mock_storage: AsyncMock, mock_user_repo: AsyncMock) -> ProfilePictureService:
    """Create profile picture service with mocks."""
    return ProfilePictureService(storage=mock_storage, user_repo=mock_user_repo)


class TestValidateImage:
    """Tests for image validation."""
    
    def test_valid_jpeg(self, profile_service: ProfilePictureService) -> None:
        """Test validation passes for valid JPEG."""
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/jpeg"
        file.size = 1024
        
        # Should not raise
        profile_service.validate_image(file)
    
    def test_invalid_content_type(self, profile_service: ProfilePictureService) -> None:
        """Test validation fails for invalid content type."""
        file = MagicMock(spec=UploadFile)
        file.content_type = "text/plain"
        file.size = 1024
        
        with pytest.raises(InvalidFileTypeError):
            profile_service.validate_image(file)
    
    def test_file_too_large(self, profile_service: ProfilePictureService) -> None:
        """Test validation fails for oversized file."""
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/jpeg"
        file.size = 10 * 1024 * 1024  # 10MB
        
        with pytest.raises(FileSizeTooLargeError):
            profile_service.validate_image(file)


class TestUploadProfilePicture:
    """Tests for profile picture upload."""
    
    @pytest.mark.asyncio
    async def test_successful_upload(
        self,
        profile_service: ProfilePictureService,
        mock_storage: AsyncMock,
    ) -> None:
        """Test successful profile picture upload."""
        image_data = create_test_image()
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/jpeg"
        file.size = len(image_data)
        file.filename = "test.jpg"
        file.read = AsyncMock(return_value=image_data)
        
        user_id = uuid4()
        result = await profile_service.upload_profile_picture(user_id, file)
        
        assert result == "/uploads/profile_pictures/test.jpg"
        mock_storage.upload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_deletes_old_picture(
        self,
        profile_service: ProfilePictureService,
        mock_storage: AsyncMock,
        mock_user_repo: AsyncMock,
    ) -> None:
        """Test old profile picture is deleted on upload."""
        # Set existing profile picture
        mock_user_repo.get_by_id.return_value.profile_picture = "/uploads/profile_pictures/old.jpg"
        
        image_data = create_test_image()
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/jpeg"
        file.size = len(image_data)
        file.filename = "new.jpg"
        file.read = AsyncMock(return_value=image_data)
        
        user_id = uuid4()
        await profile_service.upload_profile_picture(user_id, file)
        
        mock_storage.delete.assert_called_once_with("/uploads/profile_pictures/old.jpg")
```

#### 8.2 Integration Tests (`tests/routes/test_user_profile_picture.py`)

```python
"""Integration tests for user profile picture endpoints."""

from io import BytesIO
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app


def create_test_image(format: str = "JPEG") -> BytesIO:
    """Create a test image file."""
    img = Image.new("RGB", (100, 100), color="blue")
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer


@pytest.fixture
async def async_client() -> AsyncClient:
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestUploadProfilePicture:
    """Tests for profile picture upload endpoint."""
    
    @pytest.mark.asyncio
    async def test_upload_valid_image(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_user_id: uuid4,
    ) -> None:
        """Test uploading a valid image."""
        image = create_test_image()
        
        response = await async_client.post(
            f"/users/{test_user_id}/profile-picture",
            headers=auth_headers,
            files={"file": ("test.jpg", image, "image/jpeg")},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "profilePicture" in data
        assert data["profilePicture"].startswith("/uploads/")
    
    @pytest.mark.asyncio
    async def test_upload_invalid_type(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_user_id: uuid4,
    ) -> None:
        """Test uploading an invalid file type."""
        response = await async_client.post(
            f"/users/{test_user_id}/profile-picture",
            headers=auth_headers,
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_upload_unauthorized(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test uploading to another user's profile."""
        other_user_id = uuid4()
        image = create_test_image()
        
        response = await async_client.post(
            f"/users/{other_user_id}/profile-picture",
            headers=auth_headers,
            files={"file": ("test.jpg", image, "image/jpeg")},
        )
        
        assert response.status_code == 403
```

---

## Implementation Order

1. **Phase 1**: Storage configuration settings
2. **Phase 6**: Add dependencies (`python-multipart`, `Pillow`, `aiofiles`)
3. **Phase 2**: Storage service (start with local, add cloud later)
4. **Phase 3**: Profile picture service
5. **Phase 4**: Upload endpoints
6. **Phase 7**: Static files configuration
7. **Phase 8**: Tests
8. **Phase 5**: Image processing (optional enhancement)

---

## Refactoring Rules Compliance

Per `.agent/rules/python-refactoring-and-codebase-update.md`:

- ✅ **Python Best Practices**: Use Protocol for storage abstraction, SOLID principles
- ✅ **Ruff Rules**: All code must pass `ruff check` and `ruff format`
- ✅ **Full Type Hinting**: Complete type annotations using `str | None` syntax
- ✅ **Pipe Operator**: Use `|` for optional types (Python 3.10+)
- ✅ **Explicit Imports**: Use `from module import Class` pattern
- ✅ **pathlib**: Use `Path` for file operations
- ✅ **Security**: Validate file types, sizes; sanitize filenames
- ✅ **uv for Dependencies**: Use `uv add package_name`
- ✅ **HTTP Testing**: Use `ASGITransport` and `AsyncClient` for tests
- ✅ **Docstrings**: Google-style docstrings for all public functions
- ✅ **Error Handling**: Custom exceptions for upload errors
- ✅ **Async/Await**: All I/O operations use async patterns

---

## File Structure After Implementation

```plain text
app/
├── services/
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── base.py          # StorageProtocol
│   │   ├── local.py         # LocalStorage
│   │   ├── s3.py            # S3Storage (optional)
│   │   └── cloudinary.py    # CloudinaryStorage (optional)
│   └── profile_picture.py   # ProfilePictureService
├── utils/
│   └── image_processing.py  # Image validation/processing
├── errors/
│   └── upload.py            # Upload-specific exceptions
uploads/
└── profile_pictures/        # Local storage directory
tests/
├── services/
│   └── test_profile_picture.py
└── routes/
    └── test_user_profile_picture.py
```

---

## Security Considerations

1. **File Validation**: Verify MIME type matches file content (not just extension)
2. **Filename Sanitization**: Generate UUID-based filenames to prevent path traversal
3. **Size Limits**: Enforce strict file size limits (5MB max)
4. **Authorization**: Only user or admin can modify profile picture
5. **Rate Limiting**: Apply rate limits to upload endpoint
6. **Virus Scanning**: Consider ClamAV integration for production

---

## OAuth Profile Picture Flow

The current OAuth flow already handles profile pictures correctly:

1. User authenticates with Google/WeChat
2. `auth_callback()` retrieves user info including `picture` URL
3. `get_or_create_oauth_user()` passes picture URL to `UserCreate`
4. `UserRepository.create()` stores the URL in database

**No changes needed for OAuth flow** - it's already functional.

---

## Direct Email Signup Flow (New)

1. User registers via `/auth/register` (no profile picture initially)
2. User logs in and accesses profile page
3. User uploads image via `POST /users/{user_id}/profile-picture`
4. Service validates image, stores file, returns URL
5. Database updated with new profile picture URL
6. Cache invalidated for user data
