# User Media Upload Feature

## Overview

This document describes the implementation plan for user-generated media (images and videos) for **reviews** and **blog posts** in the BaliBlissed travel agency web app. The solution extends the existing storage architecture used for profile pictures.

## **Status: 📋 PLANNED**

---

## User Review Required

> [!IMPORTANT]
> **Database Schema Changes Required**
>
> This implementation requires database migrations:
>
> 1. **BlogDB** - Add `videos_url` field (currently only has `images_url`)
> 2. **ReviewDB** - Create new model (reviews don't exist as a database table yet)
>
> Please confirm the review model requirements before proceeding.

---

## Goals

1. **Review Media**: Allow users to upload images/videos when reviewing tour packages
2. **Blog Media**: Allow authenticated users to upload images/videos for blog posts
3. **Reusability**: Extend existing `StorageService` protocol for multi-media support
4. **Performance**: Video compression, thumbnails, and CDN delivery
5. **Security**: Malware scanning, content validation, size limits

---

## Architecture Overview

### Design Principles

| Principle | Implementation |
| --------- | -------------- |
| DRY | Extend existing `StorageService` protocol rather than creating new services |
| KISS | Single `MediaService` for all user media types |
| Separation of Concerns | Media processing separate from storage |
| Scalability | Cloudinary handles video transcoding and CDN |

### Storage Structure

```plain text
storage/
├── profile_pictures/     # Existing - User avatars
│   └── {user_uuid}.jpg
├── review_media/         # NEW - Review images and videos
│   └── {review_uuid}/
│       ├── {media_uuid}.jpg
│       ├── {media_uuid}_thumb.jpg
│       └── {media_uuid}.mp4
└── blog_media/           # NEW - Blog images and videos
    └── {blog_uuid}/
        ├── {media_uuid}.jpg
        ├── {media_uuid}_thumb.jpg
        └── {media_uuid}.mp4
```

---

## Implementation Plan

### Phase 0: Database Model Changes

> [!CAUTION]
> This phase requires database migrations. Run migrations on a development database first.

#### [MODIFY] [blog.py](/app/models/blog.py)

Add `videos_url` field to `BlogDB` model (line ~99):

```python
# Add after images_url field
videos_url: list[str] | None = Field(
    default=None,
    sa_column=Column(JSONB),
    description="List of video URLs",
)
```

---

#### [NEW] [review.py](/app/models/review.py)

Create new `ReviewDB` model for user reviews:

> [!NOTE]
> No `profile_picture` field needed - frontend fetches from `UserDB.profile_picture` via the `user_id` relationship.

```python
"""Review database model using SQLModel."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlmodel import Column, Field, ForeignKey, SQLModel, String


class ReviewDB(SQLModel, table=True):
    """
    Review database model for PostgreSQL.
    
    Represents user reviews for tour packages/items with ratings and media.
    Reviews can be:
    - Item-specific (item_id set) - Review for a specific tour package
    - Global (item_id is None) - General testimonial about the agency
    """

    __tablename__ = cast("declared_attr[str]", "reviews")

    __table_args__ = (
        # Unique constraint: one review per user per item (null item_id allows multiple global reviews)
        UniqueConstraint("user_id", "item_id", name="uq_reviews_user_item"),
        Index("ix_reviews_user_item", "user_id", "item_id"),
        Index("ix_reviews_rating", "rating"),
    )

    # Primary key
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        nullable=False,
        description="Review ID",
    )

    # Foreign keys
    user_id: UUID = Field(
        sa_column=Column(
            "user_id",
            ForeignKey("users.uuid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="Reviewer ID (foreign key to users.uuid)",
    )
    item_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            "item_id",
            nullable=True,  # Nullable for global reviews (testimonials)
            index=True,
        ),
        description="Item/Tour ID being reviewed (null for global reviews)",
    )

    # Review content
    rating: int = Field(
        ge=1,
        le=5,
        description="Rating from 1-5 stars",
    )
    title: str | None = Field(
        default=None,
        sa_column=Column(String(100)),
        description="Review title (optional)",
    )
    content: str = Field(
        sa_column=Column(String(5000), nullable=False),
        description="Review content",
    )

    # Media fields (stored as JSON in PostgreSQL)
    images_url: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="List of image URLs (max 5)",
    )
    video_url: str | None = Field(
        default=None,
        sa_column=Column(String(500)),
        description="Single video URL (testimonial video)",
    )

    # Metadata
    is_verified_purchase: bool = Field(
        default=False,
        description="Whether reviewer actually purchased the item",
    )
    helpful_count: int = Field(
        default=0,
        ge=0,
        description="Number of users who found this helpful",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC).replace(second=0, microsecond=0),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="Creation timestamp",
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last update timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "item_id": None,  # Global review example
                "rating": 5,
                "title": "Amazing Bali Experience!",
                "content": "BaliBlissed made our honeymoon perfect...",
                "images_url": ["https://example.com/review1.jpg"],
                "video_url": None,
                "is_verified_purchase": True,
                "helpful_count": 12,
            },
        },
    )
```

---

#### [NEW] Alembic Migration

Create migration file `alembic/versions/YYYYMMDD_HHMM_add_reviews_and_blog_videos.py`:

```python
"""Add reviews table and blog videos_url column.

Revision ID: add_reviews_blog_videos
Revises: 5f3ec632a8e7
Create Date: 2026-01-XX
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "add_reviews_blog_videos"
down_revision: str | Sequence[str] | None = "5f3ec632a8e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reviews table and videos_url to blogs."""
    # Add videos_url column to blogs table
    op.add_column(
        "blogs",
        sa.Column("videos_url", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Create reviews table
    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),  # Nullable for global reviews
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("content", sa.String(length=5000), nullable=False),
        sa.Column("images_url", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("video_url", sa.String(length=500), nullable=True),  # Single video
        sa.Column("is_verified_purchase", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("helpful_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.uuid"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "item_id", name="uq_reviews_user_item"),
    )
    
    # Create indexes
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"], unique=False)
    op.create_index("ix_reviews_item_id", "reviews", ["item_id"], unique=False)
    op.create_index("ix_reviews_user_item", "reviews", ["user_id", "item_id"], unique=False)
    op.create_index("ix_reviews_rating", "reviews", ["rating"], unique=False)
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"], unique=False)


def downgrade() -> None:
    """Remove reviews table and videos_url from blogs."""
    op.drop_index("ix_reviews_created_at", table_name="reviews")
    op.drop_index("ix_reviews_rating", table_name="reviews")
    op.drop_index("ix_reviews_user_item", table_name="reviews")
    op.drop_index("ix_reviews_item_id", table_name="reviews")
    op.drop_index("ix_reviews_user_id", table_name="reviews")
    op.drop_table("reviews")
    
    op.drop_column("blogs", "videos_url")
```

---

#### [MODIFY] [models/**init**.py](/app/models/__init__.py)

Export the new `ReviewDB` model:

```python
from app.models.review import ReviewDB

__all__ = ["BlogDB", "ReviewDB", "UserDB"]
```

---

### Phase 1: Extend Storage Protocol

#### [MODIFY] [base.py](/app/services/storage/base.py)

Add generic media upload/delete methods to `StorageService` Protocol:

```python
@abstractmethod
async def upload_media(
    self,
    entity_id: str,
    media_id: str,
    file_data: bytes,
    content_type: str,
    folder: str,  # "review_media" or "blog_media"
) -> str:
    """Upload media and return URL."""
    ...

@abstractmethod
async def delete_media(
    self,
    entity_id: str,
    media_id: str,
    folder: str,
) -> bool:
    """Delete media by ID."""
    ...

@abstractmethod
async def upload_video(
    self,
    entity_id: str,
    media_id: str,
    file_data: bytes,
    content_type: str,
    folder: str,
) -> str:
    """Upload video with transcoding and return URL."""
    ...
```

---

### Phase 2: Update Storage Implementations

#### [MODIFY] [local.py](/app/services/storage/local.py)

Add methods for generic media operations:

- `upload_media()`: Store images in `{folder}/{entity_id}/{media_id}.{ext}`
- `delete_media()`: Remove specific media file
- `upload_video()`: Store videos with thumbnail generation using ffmpeg (dev only)

#### [MODIFY] [cloudinary_storage.py](/app/services/storage/cloudinary_storage.py)

Add methods leveraging Cloudinary's features:

- `upload_media()`: Upload with auto-optimization, generate thumbnails
- `delete_media()`: Delete from Cloudinary by public_id
- `upload_video()`: Upload with automatic transcoding and adaptive streaming

---

### Phase 3: Create MediaService

#### [NEW] [media.py](/app/services/media.py)

New service class following the same pattern as `ProfilePictureService`:

```python
class MediaService:
    """Service for handling review and blog media uploads."""
    
    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or get_storage_service()
    
    def validate_image(self, file: UploadFile, file_data: bytes) -> Image.Image:
        """Validate image type, size, and content."""
        ...
    
    def validate_video(self, file: UploadFile, file_data: bytes) -> None:
        """Validate video type, size, and duration."""
        ...
    
    def process_image(self, img: Image.Image) -> tuple[bytes, str]:
        """Resize and optimize image."""
        ...
    
    async def upload_review_image(
        self,
        review_id: str,
        file: UploadFile,
    ) -> str:
        """Upload image for a review."""
        ...
    
    async def upload_review_video(
        self,
        review_id: str,
        file: UploadFile,
    ) -> str:
        """Upload video for a review."""
        ...
    
    async def upload_blog_image(
        self,
        blog_id: str,
        file: UploadFile,
    ) -> str:
        """Upload image for a blog post."""
        ...
    
    async def upload_blog_video(
        self,
        blog_id: str,
        file: UploadFile,
    ) -> str:
        """Upload video for a blog post."""
        ...
    
    async def delete_review_media(self, review_id: str, media_id: str) -> bool:
        """Delete a specific media from a review."""
        ...
    
    async def delete_blog_media(self, blog_id: str, media_id: str) -> bool:
        """Delete a specific media from a blog."""
        ...
```

---

### Phase 4: Add Configuration Settings

#### [MODIFY] [settings.py](/app/configs/settings.py)

Add media upload settings:

```python
# Review Media Settings
REVIEW_IMAGE_MAX_SIZE_MB: int = 10
REVIEW_IMAGE_MAX_COUNT: int = 5
REVIEW_VIDEO_MAX_SIZE_MB: int = 50
REVIEW_VIDEO_MAX_DURATION_SEC: int = 60  # 1 minute
REVIEW_IMAGE_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]
REVIEW_VIDEO_ALLOWED_TYPES: list[str] = ["video/mp4", "video/quicktime", "video/webm"]

# Blog Media Settings
BLOG_IMAGE_MAX_SIZE_MB: int = 10
BLOG_IMAGE_MAX_COUNT: int = 10
BLOG_VIDEO_MAX_SIZE_MB: int = 100
BLOG_VIDEO_MAX_DURATION_SEC: int = 300  # 5 minutes
BLOG_IMAGE_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp", "image/gif"]
BLOG_VIDEO_ALLOWED_TYPES: list[str] = ["video/mp4", "video/quicktime", "video/webm"]
```

---

### Phase 5: Extend Error Classes

#### [MODIFY] [upload.py](/app/errors/upload.py)

Add video-specific error classes:

```python
class VideoTooLargeError(UploadError):
    """Raised when video exceeds size limit."""
    status_code: int = 413

class VideoTooLongError(UploadError):
    """Raised when video exceeds duration limit."""
    status_code: int = 413

class UnsupportedVideoTypeError(UploadError):
    """Raised when video type is not allowed."""
    status_code: int = 415

class InvalidVideoError(UploadError):
    """Raised when video validation fails."""
    status_code: int = 400

class MediaLimitExceededError(UploadError):
    """Raised when media count limit is exceeded."""
    status_code: int = 400
```

---

### Phase 6: Create API Endpoints

#### [MODIFY] [blog.py](/app/routes/blog.py)

Add media upload endpoints for blogs:

```http
POST /blogs/{blog_id}/media/images
Content-Type: multipart/form-data
Authorization: Bearer <token>

Response: { "url": "https://...", "mediaId": "..." }
```

```http
POST /blogs/{blog_id}/media/videos
Content-Type: multipart/form-data
Authorization: Bearer <token>

Response: { "url": "https://...", "mediaId": "...", "thumbnailUrl": "..." }
```

```http
DELETE /blogs/{blog_id}/media/{media_id}
Authorization: Bearer <token>

Response: 204 No Content
```

#### [NEW] [review.py](/app/routes/review.py)

Add CRUD and media upload endpoints for reviews:

```http
POST /reviews
Content-Type: application/json
Authorization: Bearer <token>

Body: {
  "item_id": "uuid" | null,  # null for global testimonial
  "rating": 5,
  "title": "...",
  "content": "..."
}

Response: { "id": "uuid", ... }
```

```http
POST /reviews/{review_id}/media/images
POST /reviews/{review_id}/media/videos
DELETE /reviews/{review_id}/media/{media_id}
```

---

### Phase 7: Update Schemas

#### [MODIFY] [blog.py](/app/schemas/blog.py)

Add media response schemas:

```python
class MediaUploadResponse(BaseModel):
    """Response after successful media upload."""
    media_id: str
    url: str
    thumbnail_url: str | None = None
    content_type: str
    size_bytes: int

class BlogMediaResponse(BaseModel):
    """Blog media list response."""
    images: list[MediaUploadResponse] = []
    videos: list[MediaUploadResponse] = []
```

#### [NEW] [review.py](/app/schemas/review.py)

Create review schemas:

```python
class ReviewCreate(BaseModel):
    """Schema for creating a review."""
    item_id: UUID | None = Field(default=None, description="Item ID (optional for global reviews)")
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=100)
    content: str = Field(min_length=10, max_length=5000)
    images_url: list[HttpUrl] | None = None
    video_url: str | None = None

class ReviewResponse(BaseModel):
    """Schema for review response."""
    id: UUID
    user_id: UUID
    item_id: UUID | None
    rating: int
    title: str | None
    content: str
    images_url: list[HttpUrl] | None
    video_url: str | None
    helpful_count: int
    created_at: datetime
    updated_at: datetime | None
    
    # User info (fetched via relation)
    user_display_name: str
    user_profile_picture: str | None
```

---

## API Reference

### Blog Media Endpoints

| Method | Endpoint | Description | Auth |
| ------ | -------- | ----------- | ---- |
| POST | `/blogs/{blog_id}/media/images` | Upload blog image | Owner/Admin |
| POST | `/blogs/{blog_id}/media/videos` | Upload blog video | Owner/Admin |
| DELETE | `/blogs/{blog_id}/media/{media_id}` | Delete blog media | Owner/Admin |

### Review Media Endpoints

| Method | Endpoint | Description | Auth |
| ------ | -------- | ----------- | ---- |
| POST | `/reviews/{review_id}/media/images` | Upload review image | Owner/Admin |
| POST | `/reviews/{review_id}/media/videos` | Upload review video | Owner/Admin |
| DELETE | `/reviews/{review_id}/media/{media_id}` | Delete review media | Owner/Admin |

---

## Configuration Reference

| Setting | Default | Description |
| ------- | ------- | ----------- |
| `REVIEW_IMAGE_MAX_SIZE_MB` | `10` | Max review image size |
| `REVIEW_IMAGE_MAX_COUNT` | `5` | Max images per review |
| `REVIEW_VIDEO_MAX_SIZE_MB` | `50` | Max review video size |
| `REVIEW_VIDEO_MAX_DURATION_SEC` | `60` | Max review video duration |
| `BLOG_IMAGE_MAX_SIZE_MB` | `10` | Max blog image size |
| `BLOG_IMAGE_MAX_COUNT` | `10` | Max images per blog |
| `BLOG_VIDEO_MAX_SIZE_MB` | `100` | Max blog video size |
| `BLOG_VIDEO_MAX_DURATION_SEC` | `300` | Max blog video duration |

---

## Security Considerations

| Risk | Mitigation |
| ---- | ---------- |
| Malicious files | Validate content-type AND actual file content |
| Video bombs | Check duration before processing |
| Path traversal | UUID-based filenames, no user input in paths |
| Oversized uploads | Size validation before storage |
| Unauthorized access | `check_owner_or_admin()` on all operations |
| Rate limiting | 5 uploads/hour per user for videos, 20 for images |
| Content moderation | Consider Cloudinary AI moderation in production |

---

## Testing Strategy

### Existing Tests to Extend

| Existing Test | Extension |
| ------------- | --------- |
| `tests/services/test_storage.py` | Add `test_upload_media()`, `test_delete_media()`, `test_upload_video()` |
| `tests/services/test_profile_picture.py` | Use as template for `tests/services/test_media.py` |
| `tests/errors/test_upload_errors.py` | Add video error class tests |

### New Test Files

#### [NEW] `tests/services/test_media.py`

```python
# Test cases:
# - test_validate_image_valid_jpeg
# - test_validate_image_invalid_type
# - test_validate_image_too_large
# - test_validate_video_valid_mp4
# - test_validate_video_too_large
# - test_validate_video_too_long
# - test_upload_review_image
# - test_upload_review_video
# - test_upload_blog_image
# - test_upload_blog_video
# - test_delete_review_media
# - test_delete_blog_media
# - test_media_count_limit
```

#### [NEW] `tests/routes/test_blog_media.py`

```python
# Test cases:
# - test_upload_blog_image_success
# - test_upload_blog_image_unauthorized
# - test_upload_blog_image_forbidden
# - test_upload_blog_video_success
# - test_delete_blog_media_success
```

### Run Commands

```bash
# Run all media-related tests
uv run pytest tests/services/test_media.py tests/routes/test_blog_media.py -v

# Run with coverage
uv run pytest tests/services/test_media.py --cov=app/services/media --cov-report=term-missing

# Run existing storage tests (should still pass)
uv run pytest tests/services/test_storage.py -v
```

---

## Files Summary

### Database Layer (Phase 0)

| File | Action | Description |
| ---- | ------ | ----------- |
| `app/models/blog.py` | MODIFY | Add `videos_url` field |
| `app/models/review.py` | NEW | ReviewDB model with media fields |
| `app/models/__init__.py` | MODIFY | Export ReviewDB |
| `alembic/versions/YYYYMMDD_add_reviews_and_blog_videos.py` | NEW | Migration for reviews table and blog videos |

### Service Layer (Phase 1-3)

| File | Action | Description |
| ---- | ------ | ----------- |
| `app/services/storage/base.py` | MODIFY | Add generic media methods to Protocol |
| `app/services/storage/local.py` | MODIFY | Implement local media storage |
| `app/services/storage/cloudinary_storage.py` | MODIFY | Implement Cloudinary media storage |
| `app/services/media.py` | NEW | MediaService class |
| `app/services/__init__.py` | MODIFY | Export MediaService |

### Configuration & Errors (Phase 4-5)

| File | Action | Description |
| ---- | ------ | ----------- |
| `app/configs/settings.py` | MODIFY | Add media configuration |
| `app/errors/upload.py` | MODIFY | Add video error classes |
| `app/errors/__init__.py` | MODIFY | Export new errors |

### API Layer (Phase 6-7)

| File | Action | Description |
| ---- | ------ | ----------- |
| `app/schemas/blog.py` | MODIFY | Add `videos_url` and media response schemas |
| `app/schemas/review.py` | NEW | Review schemas with media fields |
| `app/routes/blog.py` | MODIFY | Add blog media endpoints |
| `app/routes/review.py` | NEW | Review CRUD and media endpoints |
| `.env.example` | MODIFY | Document new settings |

### Tests

| File | Action | Description |
| ---- | ------ | ----------- |
| `tests/models/test_review.py` | NEW | ReviewDB model tests |
| `tests/services/test_media.py` | NEW | MediaService tests |
| `tests/routes/test_blog_media.py` | NEW | Blog media endpoint tests |
| `tests/routes/test_review.py` | NEW | Review endpoint tests |

---

## Implementation Order

1. **Database Models** - Add `ReviewDB` model and `videos_url` to `BlogDB`
2. **Alembic Migration** - Create and run migration
3. **Settings & Errors** - Add media configuration and video error classes
4. **Storage Protocol** - Extend `StorageService` with new methods
5. **Storage Implementations** - Local and Cloudinary media storage
6. **MediaService** - Create the service layer
7. **Schemas** - Add review and media response schemas
8. **Routes** - Add review CRUD and media endpoints
9. **Tests** - Write comprehensive tests
10. **Documentation** - Update this file with implementation status

---

## Frontend Integration

### TypeScript Example

```typescript
// Upload blog image
async function uploadBlogImage(
  blogId: string,
  file: File,
  token: string
): Promise<MediaUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`/api/blogs/${blogId}/media/images`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

// Upload review video
async function uploadReviewVideo(
  reviewId: string,
  file: File,
  token: string,
  onProgress?: (percent: number) => void
): Promise<MediaUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);

  // Use XMLHttpRequest for progress tracking
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/reviews/${reviewId}/media/videos`);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress((e.loaded / e.total) * 100);
      }
    };
    
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(JSON.parse(xhr.responseText).detail));
      }
    };
    
    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.send(formData);
  });
}
```

---

## Dependencies

No new dependencies required. Existing packages are sufficient:

- `Pillow` - Image processing (already installed)
- `cloudinary` - Cloud storage (already installed)
- `aiofiles` - Async file I/O (already installed)

Optional for video validation in development:

```bash
# For video duration validation (development only)
# Cloudinary handles this in production
uv add python-magic  # MIME type detection
```

---

## References

- [Cloudinary Video Upload](https://cloudinary.com/documentation/python_video_upload)
- [Cloudinary Video Transformations](https://cloudinary.com/documentation/video_transformation_reference)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)
- [USER_PROFILE_PICTURE.md](file:///Users/madesuryawan/Documents/Source_Codes/Web_Dev/Unified_Backend/backend/docs/USER_PROFILE_PICTURE.md) - Existing implementation reference
