# User Profile Picture Implementation Plan

## Overview

This plan outlines the implementation of user profile picture functionality for the BaliBlissed travel agency web app. The solution is designed to be **concise, practical, and extensible** - supporting both OAuth (Google/WeChat) and direct email authentication, while laying the groundwork for future blog and review media uploads.

---

## Current State Analysis

### ✅ Already Implemented

| Component | Status | Location |
| --------- | ------ | -------- |
| Database column | ✅ | `alembic/versions/20251215_0001_initial_schema.py:41` |
| User model field | ✅ | `app/models/user.py:77-81` |
| OAuth profile picture | ✅ | `app/services/auth.py:328` - extracts `picture` from OAuth |
| UserCreate schema | ✅ | `app/schemas/user.py:158-162` |
| UserUpdate schema | ✅ | `app/schemas/user.py:224-228` |
| UserResponse schema | ✅ | `app/schemas/user.py:281` |
| Repository support | ✅ | `app/repositories/user.py:79,143-144` |
| File upload dependency | ✅ | `python-multipart` in `pyproject.toml:46` |

### ❌ What's Missing

1. File upload endpoint for manual profile picture uploads
2. File storage service (local for dev, cloud for production)
3. Image validation (type, size)
4. Default avatar generation

---

## Architecture Decisions

### Storage Strategy: Cloud-First with Local Fallback

For a travel agency handling user-generated content:

| Environment | Provider | Reason |
| ----------- | -------- | ------ |
| Development | Local filesystem | Fast iteration, no external deps |
| Production | Cloudinary | Automatic optimization, CDN delivery, image transformations |
| Future S3 | AWS S3 | If vendor lock-in is a concern |

**Why Cloudinary?**

- Automatic image optimization (WebP conversion, compression)
- On-the-fly resizing via URL parameters (`w_512,h_512,c_fill`)
- Face detection for smart cropping
- Generous free tier (25GB storage, 25GB monthly bandwidth)

### File Organization Structure

```Plain Text
storage/
├── profile_pictures/     # User avatars
│   ├── {user_uuid}.jpg
│   └── thumbs/
│       └── {user_uuid}_128x128.jpg
├── blog_images/          # Future: Blog post images
│   └── {blog_uuid}/
├── blog_videos/          # Future: Blog post videos
│   └── {blog_uuid}/
├── review_images/        # Future: Review photos
│   └── {review_uuid}/
└── review_videos/        # Future: Review videos
    └── {review_uuid}/
```

---

## Implementation Phases

### Phase 1: Storage Configuration (10 min)

**File:** [`app/configs/settings.py`](app/configs/settings.py:200)

Add to the `Settings` class:

```python
# File Storage Configuration
STORAGE_PROVIDER: Literal["local", "cloudinary"] = "local"
STORAGE_LOCAL_PATH: Path = Path("uploads")

# Cloudinary Configuration (production)
CLOUDINARY_CLOUD_NAME: str | None = None
CLOUDINARY_API_KEY: str | None = None
CLOUDINARY_API_SECRET: str | None = None

# Upload Constraints
MAX_IMAGE_SIZE_MB: int = 5
ALLOWED_IMAGE_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]
PROFILE_PICTURE_MAX_DIMENSIONS: tuple[int, int] = (512, 512)
PROFILE_PICTURE_THUMB_DIMENSIONS: tuple[int, int] = (128, 128)
```

Update `.env.example`:

```bash
# Storage Configuration
STORAGE_PROVIDER=local
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

---

### Phase 2: Storage Service (30 min)

**File:** [`app/services/storage/base.py`](app/services/storage/base.py:1)

```python
"""Storage protocol for file uploads."""

from typing import Protocol
from uuid import UUID


class StorageService(Protocol):
    """Protocol defining storage operations."""

    async def upload_profile_picture(
        self,
        user_id: UUID,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """Upload profile picture and return URL."""
        ...

    async def delete_profile_picture(self, user_id: UUID, file_url: str) -> bool:
        """Delete profile picture by URL."""
        ...

    def get_default_avatar_url(self, user_id: UUID) -> str:
        """Get default avatar URL for user."""
        ...
```

**File:** [`app/services/storage/local.py`](app/services/storage/local.py:1)

```python
"""Local filesystem storage for development."""

from pathlib import Path
from uuid import UUID

import aiofiles

from app.configs import settings


class LocalStorage:
    """Local filesystem storage implementation."""

    def __init__(self) -> None:
        self.base_path = settings.STORAGE_LOCAL_PATH
        self.profile_pictures_path = self.base_path / "profile_pictures"
        self.profile_pictures_path.mkdir(parents=True, exist_ok=True)

    async def upload_profile_picture(
        self,
        user_id: UUID,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """Store profile picture locally."""
        ext = self._get_extension(content_type)
        filename = f"{user_id}{ext}"
        file_path = self.profile_pictures_path / filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(file_data)

        return f"/uploads/profile_pictures/{filename}"

    async def delete_profile_picture(self, user_id: UUID, file_url: str) -> bool:  # noqa: ARG002
        """Delete local profile picture."""
        filename = file_url.split("/")[-1]
        file_path = self.profile_pictures_path / filename

        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def get_default_avatar_url(self, user_id: UUID) -> str:
        """Return DiceBear avatar URL for local dev."""
        return f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}"

    def _get_extension(self, content_type: str) -> str:
        """Get file extension from content type."""
        mapping = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        return mapping.get(content_type, ".jpg")
```

**File:** [`app/services/storage/cloudinary.py`](app/services/storage/cloudinary.py:1)

```python
"""Cloudinary storage for production with auto-optimization."""

from uuid import UUID

import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url

from app.configs import settings


class CloudinaryStorage:
    """Cloudinary storage with automatic image optimization."""

    def __init__(self) -> None:
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
        )
        self.folder = "baliblissed/profile_pictures"

    async def upload_profile_picture(
        self,
        user_id: UUID,
        file_data: bytes,
        content_type: str,  # noqa: ARG002
    ) -> str:
        """Upload to Cloudinary with optimization."""
        public_id = f"{self.folder}/{user_id}"

        result = cloudinary.uploader.upload(
            file_data,
            public_id=public_id,
            overwrite=True,
            resource_type="image",
            transformation=[
                {
                    "width": settings.PROFILE_PICTURE_MAX_DIMENSIONS[0],
                    "height": settings.PROFILE_PICTURE_MAX_DIMENSIONS[1],
                    "crop": "fill",
                    "gravity": "face",
                },
                {"quality": "auto", "fetch_format": "auto"},
            ],
        )

        return result["secure_url"]

    async def delete_profile_picture(self, user_id: UUID, file_url: str) -> bool:  # noqa: ARG002
        """Delete from Cloudinary."""
        public_id = f"{self.folder}/{user_id}"
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"

    def get_default_avatar_url(self, user_id: UUID) -> str:
        """Return Cloudinary-generated or DiceBear default avatar."""
        # Option 1: Use Cloudinary's placeholder
        # Option 2: Use DiceBear for consistent look
        return f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}"

    def get_profile_picture_transformed(
        self,
        user_id: UUID,
        width: int = 128,
        height: int = 128,
    ) -> str:
        """Get transformed profile picture URL (for thumbnails)."""
        public_id = f"{self.folder}/{user_id}"
        url, _ = cloudinary_url(
            public_id,
            width=width,
            height=height,
            crop="fill",
            gravity="face",
            quality="auto",
            fetch_format="auto",
        )
        return url
```

**File:** [`app/services/storage/__init__.py`](app/services/storage/__init__.py:1)

```python
"""Storage service factory."""

from app.configs import settings
from app.services.storage.cloudinary import CloudinaryStorage
from app.services.storage.local import LocalStorage

__all__ = ["get_storage_service"]


_storage_instance = None


def get_storage_service() -> LocalStorage | CloudinaryStorage:
    """Get configured storage service (singleton)."""
    global _storage_instance  # noqa: PLW0603

    if _storage_instance is None:
        if settings.STORAGE_PROVIDER == "cloudinary":
            _storage_instance = CloudinaryStorage()
        else:
            _storage_instance = LocalStorage()

    return _storage_instance
```

**Dependencies to add:**

```bash
uv add aiofiles cloudinary
```

---

### Phase 3: Upload Error Classes (10 min)

**File:** [`app/errors/upload.py`](app/errors/upload.py:1)

```python
"""Upload-specific error classes."""

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_413_REQUEST_ENTITY_TOO_LARGE


class InvalidImageError(HTTPException):
    """Raised when image validation fails."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=HTTP_400_BAD_REQUEST, detail=detail)


class ImageTooLargeError(HTTPException):
    """Raised when image exceeds size limit."""

    def __init__(self, max_size_mb: int, actual_size_mb: float) -> None:
        super().__init__(
            status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image too large: {actual_size_mb:.1f}MB. Maximum: {max_size_mb}MB",
        )


class UnsupportedImageTypeError(HTTPException):
    """Raised when image type is not allowed."""

    def __init__(self, allowed_types: list[str]) -> None:
        super().__init__(
            status_code=HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type. Allowed: {', '.join(allowed_types)}",
        )
```

**Update:** [`app/errors/__init__.py`](app/errors/__init__.py:50)

```python
from app.errors.upload import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
)

__all__ = [
    # ... existing exports ...
    "ImageTooLargeError",
    "InvalidImageError",
    "UnsupportedImageTypeError",
]
```

---

### Phase 4: Profile Picture Service (20 min)

**File:** [`app/services/profile_picture.py`](app/services/profile_picture.py:1)

```python
"""Profile picture service with validation and upload handling."""

from datetime import UTC, datetime
from io import BytesIO
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import UploadFile
from PIL import Image

from app.configs import settings
from app.errors.upload import (
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.repositories import UserRepository
from app.services.storage import get_storage_service

if TYPE_CHECKING:
    from app.services.storage.base import StorageService


class ProfilePictureService:
    """Service for handling profile picture operations."""

    def __init__(
        self,
        storage: "StorageService | None" = None,
        user_repo: UserRepository | None = None,
    ) -> None:
        self.storage = storage or get_storage_service()
        self.user_repo = user_repo

    def validate_image(self, file: UploadFile, file_data: bytes) -> None:
        """Validate image type, size, and content."""
        # Check content type
        if file.content_type not in settings.ALLOWED_IMAGE_TYPES:
            raise UnsupportedImageTypeError(settings.ALLOWED_IMAGE_TYPES)

        # Check file size
        max_size_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
        if len(file_data) > max_size_bytes:
            actual_mb = len(file_data) / (1024 * 1024)
            raise ImageTooLargeError(settings.MAX_IMAGE_SIZE_MB, actual_mb)

        # Validate image content
        try:
            img = Image.open(BytesIO(file_data))
            img.verify()
        except Exception as e:
            raise InvalidImageError("Invalid image file") from e

    def process_image(self, file_data: bytes) -> bytes:
        """Resize and optimize image for profile picture."""
        img = Image.open(BytesIO(file_data))

        # Convert to RGB if necessary
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background

        # Resize to max dimensions
        max_width, max_height = settings.PROFILE_PICTURE_MAX_DIMENSIONS
        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        # Save optimized image
        output = BytesIO()
        img.save(output, format="JPEG", quality=85, optimize=True)
        output.seek(0)

        return output.read()

    async def upload(
        self,
        user_id: UUID,
        file: UploadFile,
        user_repo: UserRepository,
    ) -> str:
        """Upload and set profile picture for user."""
        # Read file data
        file_data = await file.read()

        # Validate
        self.validate_image(file, file_data)

        # Process image
        processed_data = self.process_image(file_data)

        # Delete old picture if exists (and is local/uploaded)
        user = await user_repo.get_by_id(user_id)
        if user and user.profile_picture:
            # Only delete if it's an uploaded file, not OAuth URL
            if not user.profile_picture.startswith("http") or "googleusercontent" not in user.profile_picture:
                await self.storage.delete_profile_picture(user_id, user.profile_picture)

        # Upload new picture
        picture_url = await self.storage.upload_profile_picture(
            user_id=user_id,
            file_data=processed_data,
            content_type="image/jpeg",
        )

        # Update user record
        user.profile_picture = picture_url
        user.updated_at = datetime.now(tz=UTC).replace(second=0, microsecond=0)
        await user_repo._add_and_refresh(user)  # noqa: SLF001

        return picture_url

    async def delete(self, user_id: UUID, user_repo: UserRepository) -> bool:
        """Delete user's profile picture."""
        user = await user_repo.get_by_id(user_id)
        if not user or not user.profile_picture:
            return False

        # Delete from storage if local/uploaded
        if not user.profile_picture.startswith("http") or "googleusercontent" not in user.profile_picture:
            await self.storage.delete_profile_picture(user_id, user.profile_picture)

        # Clear profile picture
        user.profile_picture = None
        user.updated_at = datetime.now(tz=UTC).replace(second=0, microsecond=0)
        await user_repo._add_and_refresh(user)  # noqa: SLF001

        return True

    def get_default_avatar(self, user_id: UUID) -> str:
        """Get default avatar URL for user."""
        return self.storage.get_default_avatar_url(user_id)
```

**Dependencies to add:**

```bash
uv add Pillow
```

---

### Phase 5: Upload Endpoint (20 min)

**Update:** [`app/routes/user.py`](app/routes/user.py:1)

Add imports at the top:

```python
from fastapi import File, UploadFile

from app.services.profile_picture import ProfilePictureService
```

Add the endpoint:

```python
@router.post(
    "/{user_id}/profile-picture",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Upload profile picture",
    description="Upload or update user profile picture. Max 5MB, accepts JPEG/PNG/WebP.",
    responses={
        200: {
            "description": "Profile picture updated",
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "profilePicture": "https://res.cloudinary.com/.../profile_pictures/...",
                    },
                },
            },
        },
        400: {"description": "Invalid image file"},
        413: {"description": "Image too large"},
        429: {"description": "Rate limit exceeded"},
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
    file: Annotated[UploadFile, File(description="Profile picture image (JPEG/PNG/WebP, max 5MB)")],
    deps: Annotated[UserOpsDeps, Depends()],
) -> UserResponse:
    """
    Upload or update user's profile picture.

    Only the user themselves or an admin can update a profile picture.
    Image is automatically resized to 512x512 and optimized.
    """
    # Check ownership
    check_owner_or_admin(user_id, deps.current_user, "profile picture")

    # Upload picture
    profile_service = ProfilePictureService(user_repo=deps.repo)
    await profile_service.upload(user_id, file, deps.repo)

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
    description="Remove user's profile picture and revert to default avatar.",
    responses={
        204: {"description": "Profile picture deleted"},
        404: {"description": "User not found or no profile picture"},
        429: {"description": "Rate limit exceeded"},
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
) -> None:
    """Delete user's profile picture."""
    # Check ownership
    check_owner_or_admin(user_id, deps.current_user, "profile picture")

    # Delete picture
    profile_service = ProfilePictureService(user_repo=deps.repo)
    deleted = await profile_service.delete(user_id, deps.repo)

    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail="No profile picture to delete",
        )

    # Invalidate cache
    db_user = await deps.repo.get_by_id(user_id)
    if db_user:
        await get_cache_manager(request).delete(
            user_id_key(user_id),
            username_key(db_user.username),
            users_list_key(0, 10),
            namespace="users",
        )
```

---

### Phase 6: Static Files Configuration (5 min)

**Update:** [`app/main.py`](app/main.py:1)

Add imports:

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles
```

Add after app initialization:

```python
# Configure static files for local uploads
if settings.STORAGE_PROVIDER == "local":
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    app.mount(
        "/uploads",
        StaticFiles(directory="uploads"),
        name="uploads",
    )
```

---

### Phase 7: Default Avatar Support (10 min)

Update [`app/schemas/user.py`](app/schemas/user.py:281) to handle default avatars:

```python
class UserResponse(BaseModel):
    """User response model with computed default avatar."""

    # ... existing fields ...
    profile_picture: HttpUrl | None = Field(default=None, alias="profilePicture")

    @computed_field(alias="profilePicture")
    @property
    def computed_profile_picture(self) -> str:
        """Return profile picture or default avatar."""
        if self.profile_picture:
            return str(self.profile_picture)
        # Generate default avatar using DiceBear
        return f"https://api.dicebear.com/7.x/avataaars/svg?seed={self.uuid}"
```

---

## OAuth Integration

### Current Flow (Already Working)

1. User authenticates with Google/WeChat → `auth_callback()`
2. [`AuthService.get_or_create_oauth_user()`](app/services/auth.py:293) extracts `picture` from user info
3. Picture URL stored in database via `UserCreate`

### No Changes Required

The OAuth flow is already fully functional. Profile pictures from OAuth providers are stored as external URLs.

---

## Future Extensibility

### For Blog Photos/Videos

The storage service architecture supports adding new methods:

```python
# Add to StorageService protocol
async def upload_blog_media(
    self,
    blog_id: UUID,
    file_data: bytes,
    content_type: str,
    filename: str,
) -> str: ...

async def upload_review_media(
    self,
    review_id: UUID,
    file_data: bytes,
    content_type: str,
) -> str: ...
```

### File Type Support Matrix

| Feature | Images | Videos | Max Size |
| ------- | ------ | ------ | -------- |
| Profile Picture | ✅ JPEG, PNG, WebP | ❌ | 5MB |
| Blog Images | ✅ JPEG, PNG, WebP, GIF | ❌ | 10MB |
| Blog Videos | ❌ | ✅ MP4, WebM | 100MB |
| Review Photos | ✅ JPEG, PNG, WebP | ❌ | 5MB |
| Review Videos | ❌ | ✅ MP4, WebM | 50MB |

---

## Testing Strategy

### Unit Tests

**File:** `tests/services/test_profile_picture.py`

```python
"""Tests for profile picture service."""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from PIL import Image

from app.errors.upload import ImageTooLargeError, UnsupportedImageTypeError
from app.services.profile_picture import ProfilePictureService


def create_test_image(format: str = "JPEG", size: tuple[int, int] = (100, 100)) -> bytes:
    """Create a test image."""
    img = Image.new("RGB", size, color="red")
    buffer = BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer.read()


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Mock storage backend."""
    storage = AsyncMock()
    storage.upload_profile_picture.return_value = "/uploads/profile_pictures/test.jpg"
    storage.delete_profile_picture.return_value = True
    return storage


class TestValidateImage:
    """Tests for image validation."""

    def test_valid_jpeg(self, mock_storage: AsyncMock) -> None:
        """Test JPEG validation passes."""
        service = ProfilePictureService(storage=mock_storage)
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/jpeg"
        image_data = create_test_image()

        # Should not raise
        service.validate_image(file, image_data)

    def test_unsupported_type(self, mock_storage: AsyncMock) -> None:
        """Test unsupported type fails."""
        service = ProfilePictureService(storage=mock_storage)
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/bmp"

        with pytest.raises(UnsupportedImageTypeError):
            service.validate_image(file, b"fake data")

    def test_image_too_large(self, mock_storage: AsyncMock) -> None:
        """Test oversized image fails."""
        service = ProfilePictureService(storage=mock_storage)
        file = MagicMock(spec=UploadFile)
        file.content_type = "image/jpeg"
        large_data = b"x" * (10 * 1024 * 1024)  # 10MB

        with pytest.raises(ImageTooLargeError):
            service.validate_image(file, large_data)
```

### Integration Tests

**File:** `tests/routes/test_profile_picture.py`

```python
"""Integration tests for profile picture endpoints."""

from io import BytesIO
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app


def create_test_image() -> BytesIO:
    """Create test image file."""
    img = Image.new("RGB", (100, 100), color="blue")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


@pytest.mark.asyncio
async def test_upload_profile_picture(auth_headers: dict, test_user_id: str) -> None:
    """Test uploading a profile picture."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        image = create_test_image()

        response = await client.post(
            f"/users/{test_user_id}/profile-picture",
            headers=auth_headers,
            files={"file": ("test.jpg", image, "image/jpeg")},
        )

        assert response.status_code == 200
        data = response.json()
        assert "profilePicture" in data
```

---

## Deployment Checklist

### Development Setup

```bash
# 1. Install dependencies
uv add aiofiles Pillow cloudinary

# 2. No env changes needed (uses local storage by default)

# 3. Create uploads directory
mkdir -p uploads/profile_pictures

# 4. Run migrations (if needed)
alembic upgrade head

# 5. Test upload
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test-photo.jpg" \
  http://localhost:8000/users/{user_id}/profile-picture
```

### Production Setup (Cloudinary)

```bash
# 1. Create Cloudinary account at https://cloudinary.com

# 2. Add to environment variables
export STORAGE_PROVIDER=cloudinary
export CLOUDINARY_CLOUD_NAME=your_cloud_name
export CLOUDINARY_API_KEY=your_api_key
export CLOUDINARY_API_SECRET=your_api_secret

# 3. Deploy
# No local storage directory needed
```

---

## Security Considerations

| Risk | Mitigation |
| ------ | ---------- |
| File type spoofing | Validate content-type AND image content with PIL |
| Path traversal | Use UUID-based filenames, no user input in paths |
| Oversized uploads | Size check before processing (5MB limit) |
| Unauthorized access | `check_owner_or_admin()` on all operations |
| Rate limiting | 10 uploads/hour per user |
| Cache poisoning | Cache invalidation on upload/delete |
| Image bombs | PIL verify + max dimensions check |

---

## Summary

| Component | Lines of Code | File |
| --------- | ------------- | ---- |
| Settings | +15 | [`app/configs/settings.py`](app/configs/settings.py) |
| Storage protocol | +15 | [`app/services/storage/base.py`](app/services/storage/base.py) |
| Local storage | +40 | [`app/services/storage/local.py`](app/services/storage/local.py) |
| Cloudinary storage | +50 | [`app/services/storage/cloudinary.py`](app/services/storage/cloudinary.py) |
| Storage factory | +15 | [`app/services/storage/__init__.py`](app/services/storage/__init__.py) |
| Error classes | +25 | [`app/errors/upload.py`](app/errors/upload.py) |
| Profile service | +80 | [`app/services/profile_picture.py`](app/services/profile_picture.py) |
| Upload endpoint | +60 | [`app/routes/user.py`](app/routes/user.py) |
| Static files | +8 | [`app/main.py`](app/main.py) |
| **Total** | **~308** | **9 files** |

---

## References

- [Cloudinary Python SDK](https://cloudinary.com/documentation/python_integration)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)
- [Pillow Image Processing](https://pillow.readthedocs.io/)
- [DiceBear Avatars](https://www.dicebear.com/)
