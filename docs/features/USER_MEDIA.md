# User Media Upload Feature

## Overview

This document describes the implementation plan for user-generated media for **reviews** (images only) and **blog posts** (images + videos) in the BaliBlissed travel agency web app. The solution extends the existing storage architecture used for profile pictures.

## **Status: 📋 PLANNED**

---

## Design Decisions

| Decision | Rationale |
| -------- | --------- |
| **Reviews: Images only** | Travel agency reviews rarely need video; reduces complexity |
| **Blogs: Images + Videos** | Authors/admins may embed travel videos in blog content |
| **Reuse existing storage** | Extend `StorageService` protocol - no new abstractions |
| **Cloudinary for videos** | Automatic transcoding, CDN delivery, no server-side processing |

---

## Storage Structure

```text
storage/
├── profile_pictures/     # Existing
│   └── {user_uuid}.jpg
├── review_images/        # NEW - Review photos
│   └── {review_uuid}/
│       └── {media_uuid}.jpg
└── blog_media/           # NEW - Blog images and videos
    └── {blog_uuid}/
        ├── {media_uuid}.jpg
        └── {media_uuid}.mp4
```

---

## Implementation Plan

### Phase 1: Database Changes

#### 1.1 Add `videos_url` to BlogDB

**File:** `app/models/blog.py` (after line 102)

```python
videos_url: list[str] | None = Field(
    default=None,
    sa_column=Column(JSONB),
    description="List of video URLs (max 3)",
)
```

#### 1.2 Create ReviewDB Model

**File:** `app/models/review.py` (NEW)

```python
"""Review database model."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlmodel import Column, Field, ForeignKey, SQLModel, String


class ReviewDB(SQLModel, table=True):
    """User review for tour packages."""

    __tablename__ = cast("declared_attr[str]", "reviews")

    __table_args__ = (
        Index("ix_reviews_user_item", "user_id", "item_id"),
        Index("ix_reviews_rating", "rating"),
        Index("ix_reviews_created_at", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    user_id: UUID = Field(
        sa_column=Column(
            ForeignKey("users.uuid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    )
    item_id: UUID | None = Field(
        default=None,
        sa_column=Column(nullable=True, index=True),
        description="Tour package ID (null for general testimonials)",
    )

    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, sa_column=Column(String(100)))
    content: str = Field(sa_column=Column(String(2000), nullable=False))

    images_url: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Review images (max 5)",
    )

    is_verified_purchase: bool = Field(default=False)
    helpful_count: int = Field(default=0, ge=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )

    model_config = ConfigDict(from_attributes=True)
```

#### 1.3 Alembic Migration

**File:** `alembic/versions/YYYYMMDD_add_reviews_and_blog_videos.py`

```python
"""Add reviews table and blog videos_url.

Revision ID: add_reviews_blog_videos
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "add_reviews_blog_videos"
down_revision = "5f3ec632a8e7"  # Update to latest


def upgrade() -> None:
    # Blog videos
    op.add_column(
        "blogs",
        sa.Column("videos_url", postgresql.JSONB(), nullable=True),
    )

    # Reviews table
    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(100), nullable=True),
        sa.Column("content", sa.String(2000), nullable=False),
        sa.Column("images_url", postgresql.JSONB(), nullable=True),
        sa.Column("is_verified_purchase", sa.Boolean(), server_default="false"),
        sa.Column("helpful_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])
    op.create_index("ix_reviews_item_id", "reviews", ["item_id"])
    op.create_index("ix_reviews_user_item", "reviews", ["user_id", "item_id"])
    op.create_index("ix_reviews_rating", "reviews", ["rating"])
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"])


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_column("blogs", "videos_url")
```

---

### Phase 2: Extend Storage & Services

#### 2.1 Extend StorageService Protocol

**File:** `app/services/storage/base.py` (add methods)

```python
@abstractmethod
async def upload_media(
    self,
    folder: str,
    entity_id: str,
    media_id: str,
    file_data: bytes,
    content_type: str,
) -> str:
    """Upload image/video to folder/{entity_id}/{media_id}.ext"""
    ...

@abstractmethod
async def delete_media(self, folder: str, entity_id: str, media_id: str) -> bool:
    """Delete media file."""
    ...
```

#### 2.2 Implement in LocalStorage and CloudinaryStorage

Extend both implementations following the existing `upload_profile_picture` pattern.

#### 2.3 Create MediaService

**File:** `app/services/media.py` (NEW)

```python
"""Media upload service for reviews and blogs."""

from uuid import uuid4

from fastapi import UploadFile
from PIL import Image

from app.configs.settings import settings
from app.errors.upload import (
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
)
from app.services.storage import get_storage_service


class MediaService:
    """Handles image uploads for reviews and blogs."""

    def __init__(self) -> None:
        self.storage = get_storage_service()

    async def upload_review_image(self, review_id: str, file: UploadFile) -> str:
        """Upload image for a review (max 5 images, 5MB each)."""
        return await self._upload_image(
            folder="review_images",
            entity_id=review_id,
            file=file,
            max_size_mb=settings.MEDIA_IMAGE_MAX_SIZE_MB,
        )

    async def upload_blog_image(self, blog_id: str, file: UploadFile) -> str:
        """Upload image for a blog post."""
        return await self._upload_image(
            folder="blog_media",
            entity_id=blog_id,
            file=file,
            max_size_mb=settings.MEDIA_IMAGE_MAX_SIZE_MB,
        )

    async def upload_blog_video(self, blog_id: str, file: UploadFile) -> str:
        """Upload video for a blog post (Cloudinary handles transcoding)."""
        media_id = str(uuid4())
        file_data = await file.read()

        # Basic validation - Cloudinary handles the rest
        if len(file_data) > settings.MEDIA_VIDEO_MAX_SIZE_MB * 1024 * 1024:
            raise ImageTooLargeError(settings.MEDIA_VIDEO_MAX_SIZE_MB)

        return await self.storage.upload_media(
            folder="blog_media",
            entity_id=blog_id,
            media_id=media_id,
            file_data=file_data,
            content_type=file.content_type or "video/mp4",
        )

    async def delete_media(self, folder: str, entity_id: str, media_id: str) -> bool:
        """Delete a media file."""
        return await self.storage.delete_media(folder, entity_id, media_id)

    async def _upload_image(
        self,
        folder: str,
        entity_id: str,
        file: UploadFile,
        max_size_mb: int,
    ) -> str:
        """Common image upload logic."""
        # Validate content type
        allowed = settings.MEDIA_IMAGE_ALLOWED_TYPES
        if file.content_type not in allowed:
            raise UnsupportedImageTypeError(file.content_type or "unknown", allowed)

        file_data = await file.read()

        # Validate size
        if len(file_data) > max_size_mb * 1024 * 1024:
            raise ImageTooLargeError(max_size_mb)

        # Validate image content
        try:
            img = Image.open(file_data)
            img.verify()
        except Exception as e:
            raise InvalidImageError() from e

        media_id = str(uuid4())
        return await self.storage.upload_media(
            folder=folder,
            entity_id=entity_id,
            media_id=media_id,
            file_data=file_data,
            content_type=file.content_type or "image/jpeg",
        )
```

---

### Phase 3: Configuration & API

#### 3.1 Add Settings

**File:** `app/configs/settings.py` (add)

```python
# Media Upload Settings
MEDIA_IMAGE_MAX_SIZE_MB: int = 5
MEDIA_IMAGE_MAX_COUNT_REVIEW: int = 5
MEDIA_IMAGE_MAX_COUNT_BLOG: int = 10
MEDIA_VIDEO_MAX_SIZE_MB: int = 50
MEDIA_VIDEO_MAX_COUNT_BLOG: int = 3
MEDIA_IMAGE_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]
MEDIA_VIDEO_ALLOWED_TYPES: list[str] = ["video/mp4", "video/quicktime"]
```

#### 3.2 Add Error Classes

**File:** `app/errors/upload.py` (add)

```python
class MediaLimitExceededError(UploadError):
    """Raised when media count limit exceeded."""

    def __init__(self, max_count: int, media_type: str = "images") -> None:
        super().__init__(
            detail=f"Maximum {max_count} {media_type} allowed",
            status_code=HTTP_400_BAD_REQUEST,
        )
```

#### 3.3 Review Schemas

**File:** `app/schemas/review.py` (NEW)

```python
"""Review schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ReviewCreate(BaseModel):
    """Create review request."""

    item_id: UUID | None = Field(default=None, description="Tour package ID")
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=100)
    content: str = Field(min_length=10, max_length=2000)


class ReviewResponse(BaseModel):
    """Review response."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    user_id: UUID = Field(alias="userId")
    item_id: UUID | None = Field(alias="itemId")
    rating: int
    title: str | None
    content: str
    images_url: list[HttpUrl] | None = Field(default=None, alias="imagesUrl")
    helpful_count: int = Field(alias="helpfulCount")
    created_at: datetime = Field(alias="createdAt")


class MediaUploadResponse(BaseModel):
    """Media upload response."""

    media_id: str = Field(alias="mediaId")
    url: str
```

#### 3.4 API Endpoints

**Blog media endpoints** (add to `app/routes/blog.py`):

```python
@router.post("/{blog_id}/images", response_model=MediaUploadResponse)
async def upload_blog_image(blog_id: UUID, file: UploadFile, deps: BlogOpsDeps):
    """Upload image to blog post."""
    ...

@router.post("/{blog_id}/videos", response_model=MediaUploadResponse)
async def upload_blog_video(blog_id: UUID, file: UploadFile, deps: BlogOpsDeps):
    """Upload video to blog post (authors/admins only)."""
    ...

@router.delete("/{blog_id}/media/{media_id}", status_code=204)
async def delete_blog_media(blog_id: UUID, media_id: str, deps: BlogOpsDeps):
    """Delete media from blog post."""
    ...
```

**Review endpoints** (new file `app/routes/review.py`):

```python
@router.post("/", response_model=ReviewResponse, status_code=201)
async def create_review(data: ReviewCreate, deps: ReviewOpsDeps):
    """Create a new review."""
    ...

@router.post("/{review_id}/images", response_model=MediaUploadResponse)
async def upload_review_image(review_id: UUID, file: UploadFile, deps: ReviewOpsDeps):
    """Upload image to review (max 5)."""
    ...

@router.delete("/{review_id}/images/{media_id}", status_code=204)
async def delete_review_image(review_id: UUID, media_id: str, deps: ReviewOpsDeps):
    """Delete image from review."""
    ...
```

---

## API Reference

| Method | Endpoint | Description | Auth |
| ------ | -------- | ----------- | ---- |
| POST | `/reviews` | Create review | User |
| GET | `/reviews` | List reviews | Public |
| POST | `/reviews/{id}/images` | Upload review image | Owner |
| DELETE | `/reviews/{id}/images/{media_id}` | Delete review image | Owner/Admin |
| POST | `/blogs/{id}/images` | Upload blog image | Author/Admin |
| POST | `/blogs/{id}/videos` | Upload blog video | Author/Admin |
| DELETE | `/blogs/{id}/media/{media_id}` | Delete blog media | Author/Admin |

---

## Configuration

| Setting | Default | Description |
| ------- | ------- | ----------- |
| `MEDIA_IMAGE_MAX_SIZE_MB` | `5` | Max image size |
| `MEDIA_IMAGE_MAX_COUNT_REVIEW` | `5` | Max images per review |
| `MEDIA_IMAGE_MAX_COUNT_BLOG` | `10` | Max images per blog |
| `MEDIA_VIDEO_MAX_SIZE_MB` | `50` | Max video size |
| `MEDIA_VIDEO_MAX_COUNT_BLOG` | `3` | Max videos per blog |

---

## Security

| Risk | Mitigation |
| ---- | ---------- |
| Invalid files | Validate content-type + PIL verify |
| Oversized uploads | Size check before storage |
| Path traversal | UUID-based filenames only |
| Unauthorized access | `check_owner_or_admin()` |
| Rate limiting | 20 images/hour, 5 videos/hour |

---

## Files Summary

| File | Action | Description |
| ---- | ------ | ----------- |
| `app/models/blog.py` | MODIFY | Add `videos_url` |
| `app/models/review.py` | NEW | ReviewDB model |
| `app/models/__init__.py` | MODIFY | Export ReviewDB |
| `alembic/versions/...` | NEW | Migration |
| `app/services/storage/base.py` | MODIFY | Add `upload_media`, `delete_media` |
| `app/services/storage/local.py` | MODIFY | Implement new methods |
| `app/services/storage/cloudinary_storage.py` | MODIFY | Implement new methods |
| `app/services/media.py` | NEW | MediaService |
| `app/configs/settings.py` | MODIFY | Add media settings |
| `app/errors/upload.py` | MODIFY | Add MediaLimitExceededError |
| `app/schemas/review.py` | NEW | Review schemas |
| `app/schemas/blog.py` | MODIFY | Add MediaUploadResponse |
| `app/routes/review.py` | NEW | Review endpoints |
| `app/routes/blog.py` | MODIFY | Add media endpoints |

---

## Testing

```bash
# Run media tests
uv run pytest tests/services/test_media.py tests/routes/test_review.py -v

# Run with coverage
uv run pytest tests/services/test_media.py --cov=app/services/media
```

---

## References

- [USER_PROFILE_PICTURE.md](./USER_PROFILE_PICTURE.md) - Existing implementation
- [Cloudinary Video Upload](https://cloudinary.com/documentation/python_video_upload)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)
