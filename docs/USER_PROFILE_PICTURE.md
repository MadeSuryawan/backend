# User Profile Picture Feature

## Overview

This document describes the **fully implemented** user profile picture functionality for the BaliBlissed travel agency web app. The solution supports both OAuth (Google/WeChat) and direct email authentication, with a flexible storage backend (local for development, Cloudinary for production).

## **Status: ✅ IMPLEMENTED**

---

## Implementation Summary

### Components Implemented

| Component | Status | Location |
| --------- | ------ | -------- |
| Database column | ✅ | `alembic/versions/20251215_0001_initial_schema.py:41` |
| User model field | ✅ | `app/models/user.py:77-81` |
| OAuth profile picture | ✅ | `app/services/auth.py:328` |
| Configuration settings | ✅ | `app/configs/settings.py` |
| Storage protocol | ✅ | `app/services/storage/base.py` |
| Local storage | ✅ | `app/services/storage/local.py` |
| Cloudinary storage | ✅ | `app/services/storage/cloudinary_storage.py` |
| Storage factory | ✅ | `app/services/storage/__init__.py` |
| Error classes | ✅ | `app/errors/upload.py` |
| Profile picture service | ✅ | `app/services/profile_picture.py` |
| Upload endpoint | ✅ | `app/routes/user.py` |
| Delete endpoint | ✅ | `app/routes/user.py` |
| Static files mount | ✅ | `app/main.py` |
| Unit tests | ✅ | `tests/services/test_profile_picture.py` |
| Storage tests | ✅ | `tests/services/test_storage.py` |
| Error tests | ✅ | `tests/errors/test_upload_errors.py` |
| Route tests | ✅ | `tests/routes/test_profile_picture.py` |

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

## API Endpoints

### Upload Profile Picture

```http
POST /users/{user_id}/profile-picture
Content-Type: multipart/form-data
Authorization: Bearer <token>
```

**Request:**

- `file`: Image file (JPEG, PNG, or WebP, max 5MB)

**Response (200 OK):**

```json
{
  "uuid": "123e4567-e89b-12d3-a456-426614174000",
  "username": "johndoe",
  "email": "john@example.com",
  "profilePicture": "https://res.cloudinary.com/.../profile_pictures/123e4567.jpg",
  "firstName": "John",
  "lastName": "Doe",
  "role": "user",
  "isActive": true,
  "isVerified": true,
  "createdAt": "2024-01-15T10:30:00Z",
  "updatedAt": "2024-01-20T14:45:00Z"
}
```

**Error Responses:**

- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: Not authorized to update this user's profile picture
- `413 Request Entity Too Large`: Image exceeds 5MB limit
- `415 Unsupported Media Type`: Invalid image type (not JPEG/PNG/WebP)
- `429 Too Many Requests`: Rate limit exceeded (10 uploads/hour)

### Delete Profile Picture

```http
DELETE /users/{user_id}/profile-picture
Authorization: Bearer <token>
```

**Response (204 No Content):** Empty body on success

**Error Responses:**

- `400 Bad Request`: No profile picture to delete
- `401 Unauthorized`: Missing or invalid authentication token
- `403 Forbidden`: Not authorized to delete this user's profile picture
- `429 Too Many Requests`: Rate limit exceeded

---

## Frontend Integration Guide

### JavaScript/TypeScript Example

```typescript
// Upload profile picture
async function uploadProfilePicture(userId: string, file: File, token: string): Promise<User> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`/api/users/${userId}/profile-picture`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

// Delete profile picture
async function deleteProfilePicture(userId: string, token: string): Promise<void> {
  const response = await fetch(`/api/users/${userId}/profile-picture`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Delete failed');
  }
}

// Get default avatar URL for users without profile pictures
function getDefaultAvatarUrl(userId: string, username?: string): string {
  const seed = encodeURIComponent(username || userId);
  return `https://api.dicebear.com/9.x/initials/svg?seed=${seed}&backgroundColor=0ea5e9,14b8a6,8b5cf6,f59e0b,ef4444&backgroundType=gradientLinear&fontWeight=500`;
}
```

### React Component Example

```tsx
import { useState, useRef } from 'react';

interface ProfilePictureUploaderProps {
  userId: string;
  currentPicture?: string;
  username: string;
  onUploadSuccess: (user: User) => void;
}

export function ProfilePictureUploader({
  userId,
  currentPicture,
  username,
  onUploadSuccess,
}: ProfilePictureUploaderProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Get display URL (uploaded picture or default avatar)
  const displayUrl = currentPicture || getDefaultAvatarUrl(userId, username);

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Client-side validation
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('Please select a JPEG, PNG, or WebP image');
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      setError('Image must be less than 5MB');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const token = localStorage.getItem('accessToken');
      const updatedUser = await uploadProfilePicture(userId, file, token!);
      onUploadSuccess(updatedUser);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="profile-picture-uploader">
      <img
        src={displayUrl}
        alt={`${username}'s profile`}
        className="profile-picture"
        style={{ width: 128, height: 128, borderRadius: '50%' }}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={handleFileSelect}
        style={{ display: 'none' }}
      />

      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
      >
        {isUploading ? 'Uploading...' : 'Change Picture'}
      </button>

      {error && <p className="error">{error}</p>}
    </div>
  );
}
```

### Vue.js Example

```vue
<template>
  <div class="profile-picture-uploader">
    <img
      :src="displayUrl"
      :alt="`${username}'s profile`"
      class="profile-picture"
    />

    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      @change="handleFileSelect"
      style="display: none"
    />

    <button @click="$refs.fileInput.click()" :disabled="isUploading">
      {{ isUploading ? 'Uploading...' : 'Change Picture' }}
    </button>

    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const props = defineProps<{
  userId: string;
  currentPicture?: string;
  username: string;
}>();

const emit = defineEmits<{
  uploadSuccess: [user: User];
}>();

const isUploading = ref(false);
const error = ref<string | null>(null);

const displayUrl = computed(() =>
  props.currentPicture || getDefaultAvatarUrl(props.userId, props.username)
);

async function handleFileSelect(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;

  // Validation and upload logic similar to React example
  // ...
}
</script>
```

---

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
# Storage Configuration
STORAGE_PROVIDER=local                    # Options: local, cloudinary
UPLOADS_DIR=uploads                       # Local storage directory

# Cloudinary Configuration (for production)
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret

# Profile Picture Settings
PROFILE_PICTURE_MAX_SIZE_MB=5             # Maximum file size in MB
PROFILE_PICTURE_MAX_DIMENSION=1024        # Maximum width/height in pixels
PROFILE_PICTURE_QUALITY=85                # JPEG quality (1-100)
PROFILE_PICTURE_ALLOWED_TYPES=image/jpeg,image/png,image/webp
```

### Settings Reference

| Setting | Default | Description |
| ------- | ------- | ----------- |
| `STORAGE_PROVIDER` | `local` | Storage backend (`local` or `cloudinary`) |
| `UPLOADS_DIR` | `uploads` | Local storage directory path |
| `PROFILE_PICTURE_MAX_SIZE_MB` | `5` | Maximum upload size in MB |
| `PROFILE_PICTURE_MAX_DIMENSION` | `1024` | Maximum image dimension (width/height) |
| `PROFILE_PICTURE_QUALITY` | `85` | JPEG compression quality |
| `PROFILE_PICTURE_ALLOWED_TYPES` | `image/jpeg,image/png,image/webp` | Allowed MIME types |

---

## Implementation Details

### Storage Service Architecture

The storage system uses a Protocol-based design for flexibility:

```python
# app/services/storage/base.py
from typing import Protocol


class StorageService(Protocol):
    """Protocol defining storage operations."""

    async def upload_profile_picture(
        self,
        user_id: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """Upload profile picture and return URL."""
        ...

    async def delete_profile_picture(self, user_id: str, file_url: str) -> bool:
        """Delete profile picture by URL."""
        ...

    async def get_profile_picture_url(self, user_id: str) -> str | None:
        """Get profile picture URL for user."""
        ...
```

### Local Storage (Development)

```python
# app/services/storage/local.py
class LocalStorage:
    """Local filesystem storage implementation."""

    def __init__(self, base_path: Path | None = None) -> None:
        self.base_path = base_path or Path(settings.UPLOADS_DIR)
        self.profile_pictures_path = self.base_path / "profile_pictures"
        self.profile_pictures_path.mkdir(parents=True, exist_ok=True)

    async def upload_profile_picture(
        self,
        user_id: str,
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
```

### Cloudinary Storage (Production)

```python
# app/services/storage/cloudinary_storage.py
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
        user_id: str,
        file_data: bytes,
        content_type: str,
    ) -> str:
        """Upload to Cloudinary with optimization."""
        public_id = f"{self.folder}/{user_id}"

        result = cloudinary.uploader.upload(
            file_data,
            public_id=public_id,
            overwrite=True,
            resource_type="image",
            transformation=[
                {"width": 512, "height": 512, "crop": "fill", "gravity": "face"},
                {"quality": "auto", "fetch_format": "auto"},
            ],
        )

        return result["secure_url"]
```

### Storage Factory

```python
# app/services/storage/__init__.py
_storage_instance: LocalStorage | CloudinaryStorage | None = None

def get_storage_service() -> LocalStorage | CloudinaryStorage:
    """Get configured storage service (singleton)."""
    global _storage_instance

    if _storage_instance is None:
        if settings.STORAGE_PROVIDER == "cloudinary":
            _storage_instance = CloudinaryStorage()
        else:
            _storage_instance = LocalStorage()

    return _storage_instance
```

---

### Profile Picture Service

The `ProfilePictureService` handles validation, processing, and storage operations:

```python
# app/services/profile_picture.py
class ProfilePictureService:
    """Service for handling profile picture operations."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or get_storage_service()

    def validate_image(self, file: UploadFile, file_data: bytes) -> None:
        """Validate image type, size, and content."""
        # Check content type
        if file.content_type not in settings.PROFILE_PICTURE_ALLOWED_TYPES:
            raise UnsupportedImageTypeError(file.content_type)

        # Check file size
        max_size_bytes = settings.PROFILE_PICTURE_MAX_SIZE_MB * 1024 * 1024
        if len(file_data) > max_size_bytes:
            actual_mb = len(file_data) / (1024 * 1024)
            raise ImageTooLargeError(settings.PROFILE_PICTURE_MAX_SIZE_MB, actual_mb)

        # Validate image content with PIL
        try:
            img = Image.open(BytesIO(file_data))
            img.verify()
        except Exception as e:
            raise InvalidImageError("Invalid or corrupted image file") from e

    def process_image(self, file_data: bytes) -> tuple[bytes, str]:
        """Resize and optimize image. Returns (processed_data, content_type)."""
        img = Image.open(BytesIO(file_data))

        # Convert to RGB if necessary (for PNG with transparency)
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
            img = background

        # Resize to max dimensions
        max_dim = settings.PROFILE_PICTURE_MAX_DIMENSION
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        # Save optimized JPEG
        output = BytesIO()
        img.save(output, format="JPEG", quality=settings.PROFILE_PICTURE_QUALITY, optimize=True)
        output.seek(0)

        return output.read(), "image/jpeg"

    @staticmethod
    def get_default_avatar_url(seed: str) -> str:
        """Generate DiceBear avatar URL with initials style."""
        encoded_seed = urllib.parse.quote(seed)
        return (
            f"https://api.dicebear.com/9.x/initials/svg"
            f"?seed={encoded_seed}"
            f"&backgroundColor=0ea5e9,14b8a6,8b5cf6,f59e0b,ef4444"
            f"&backgroundType=gradientLinear"
            f"&fontWeight=500"
        )
```

---

### Error Classes

```python
# app/errors/upload.py
class UploadError(AppError):
    """Base class for upload-related errors."""
    status_code: int = 500
    detail: str = "Upload failed"

class ImageTooLargeError(UploadError):
    """Raised when image exceeds size limit."""
    status_code: int = 413

class UnsupportedImageTypeError(UploadError):
    """Raised when image type is not allowed."""
    status_code: int = 415

class InvalidImageError(UploadError):
    """Raised when image validation fails."""
    status_code: int = 400

class ImageProcessingError(UploadError):
    """Raised when image processing fails."""
    status_code: int = 422

class StorageError(UploadError):
    """Raised when storage operation fails."""
    status_code: int = 500
    detail: str = "Storage operation failed"

class NoProfilePictureError(UploadError):
    """Raised when trying to delete non-existent profile picture."""
    status_code: int = 400
    detail: str = "No profile picture to delete"
```

---

## Default Avatar (DiceBear)

When a user doesn't have a profile picture, the backend returns a DiceBear URL using the "initials" style:

```text
https://api.dicebear.com/9.x/initials/svg?seed={username}&backgroundColor=0ea5e9,14b8a6,8b5cf6,f59e0b,ef4444&backgroundType=gradientLinear&fontWeight=500
```

**Features:**

- Uses DiceBear v9 API
- "initials" style shows user's initials
- Gradient background with brand colors
- Consistent across all platforms
- No storage required

---

## Testing

### Test Files Created

| File | Tests | Description |
| ---- | ----- | ----------- |
| `tests/services/test_profile_picture.py` | 28 | ProfilePictureService unit tests |
| `tests/services/test_storage.py` | 8 | LocalStorage unit tests |
| `tests/errors/test_upload_errors.py` | 17 | Upload error class tests |
| `tests/routes/test_profile_picture.py` | 4 | API endpoint tests |

### Running Tests

```bash
# Run all profile picture tests
uv run pytest tests/services/test_profile_picture.py tests/services/test_storage.py tests/errors/test_upload_errors.py tests/routes/test_profile_picture.py -v

# Run with coverage
uv run pytest tests/services/test_profile_picture.py --cov=app/services/profile_picture --cov-report=term-missing
```

### Test Coverage

- ✅ Image validation (type, size, content)
- ✅ Image processing (resize, format conversion)
- ✅ Default avatar URL generation
- ✅ Local storage operations
- ✅ Error handling
- ✅ Authentication requirements

---

## Deployment

### Development Setup

```bash
# 1. Install dependencies (already done)
uv add aiofiles Pillow cloudinary

# 2. Uses local storage by default (STORAGE_PROVIDER=local)

# 3. Uploads directory created automatically

# 4. Test upload
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test-photo.jpg" \
  http://localhost:8000/users/{user_id}/profile-picture
```

### Production Setup (Cloudinary)

```bash
# Set environment variables
export STORAGE_PROVIDER=cloudinary
export CLOUDINARY_CLOUD_NAME=your_cloud_name
export CLOUDINARY_API_KEY=your_api_key
export CLOUDINARY_API_SECRET=your_api_secret
```

---

## Security

| Risk | Mitigation |
| ---- | ---------- |
| File type spoofing | Validate content-type AND image content with PIL |
| Path traversal | Use UUID-based filenames, no user input in paths |
| Oversized uploads | Size check before processing (5MB limit) |
| Unauthorized access | `check_owner_or_admin()` on all operations |
| Rate limiting | 10 uploads/hour per user |
| Cache poisoning | Cache invalidation on upload/delete |
| Image bombs | PIL verify + max dimensions check |

---

## Files Modified/Created

| File | Status | Description |
| ---- | ------ | ----------- |
| `app/configs/settings.py` | Modified | Added storage configuration |
| `.env.example` | Modified | Added Cloudinary env vars |
| `app/services/storage/__init__.py` | Created | Storage factory |
| `app/services/storage/base.py` | Created | StorageService protocol |
| `app/services/storage/local.py` | Created | Local storage implementation |
| `app/services/storage/cloudinary_storage.py` | Created | Cloudinary implementation |
| `app/errors/upload.py` | Created | Upload error classes |
| `app/errors/__init__.py` | Modified | Export upload errors |
| `app/services/profile_picture.py` | Created | Profile picture service |
| `app/services/__init__.py` | Modified | Export ProfilePictureService |
| `app/routes/user.py` | Modified | Upload/delete endpoints |
| `app/schemas/user.py` | Modified | Updated profile_picture field |
| `app/main.py` | Modified | Static files mount |

---

## References

- [Cloudinary Python SDK](https://cloudinary.com/documentation/python_integration)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)
- [Pillow Image Processing](https://pillow.readthedocs.io/)
- [DiceBear Avatars v9](https://www.dicebear.com/styles/initials/)
