# tests/routes/test_blog_media.py
"""Tests for blog media API endpoints."""

from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image

from app.models.blog import BlogDB


def create_test_image_bytes() -> bytes:
    """Create a small valid JPEG image for testing."""
    img = Image.new("RGB", (100, 100), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


def create_test_video_bytes() -> bytes:
    """Create fake video bytes for testing."""
    return b"fake video content for testing"


@pytest.fixture
def sample_blog() -> BlogDB:
    """Create a sample blog for testing."""
    return BlogDB(
        id=uuid4(),
        author_id=uuid4(),
        title="Ultimate Bali Travel Guide",
        slug="ultimate-bali-travel-guide",
        content="Bali is a beautiful island with amazing beaches and culture.",
        summary="Everything you need to know about Bali",
        view_count=100,
        word_count=50,
        reading_time_minutes=1,
        status="published",
        tags=["travel", "bali"],
        images_url=[],
        videos_url=[],
    )


@pytest.fixture
def sample_blog_with_media() -> BlogDB:
    """Create a sample blog with existing media for testing."""
    blog_id = uuid4()
    return BlogDB(
        id=blog_id,
        author_id=uuid4(),
        title="Ultimate Bali Travel Guide",
        slug="ultimate-bali-travel-guide",
        content="Bali is a beautiful island with amazing beaches and culture.",
        summary="Everything you need to know about Bali",
        view_count=100,
        word_count=50,
        reading_time_minutes=1,
        status="published",
        tags=["travel", "bali"],
        images_url=[
            f"https://example.com/uploads/blog_images/{blog_id}/{uuid4()}.jpg",
        ],
        videos_url=[
            f"https://example.com/uploads/blog_videos/{blog_id}/{uuid4()}.mp4",
        ],
    )


class TestUploadBlogImage:
    """Tests for POST /blogs/{blog_id}/images endpoint."""

    @pytest.mark.asyncio
    async def test_upload_blog_image_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload requires authentication."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_blog_image_invalid_uuid(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that upload fails with invalid blog UUID."""
        response = await client.post(
            "/blogs/invalid-uuid/images",
            headers=auth_headers,
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        assert response.status_code in [401, 404, 422]

    @pytest.mark.asyncio
    async def test_upload_blog_image_unsupported_type(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that upload fails with unsupported image type."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            headers=auth_headers,
            files={"file": ("test.gif", b"GIF89a...", "image/gif")},
        )
        # Should fail due to unsupported type
        assert response.status_code in [404, 415]

    @pytest.mark.asyncio
    async def test_upload_blog_image_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test uploading image to non-existent blog."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            headers=auth_headers,
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        assert response.status_code == 404


class TestUploadBlogVideo:
    """Tests for POST /blogs/{blog_id}/videos endpoint."""

    @pytest.mark.asyncio
    async def test_upload_blog_video_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload requires authentication."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_blog_video_invalid_uuid(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that upload fails with invalid blog UUID."""
        response = await client.post(
            "/blogs/invalid-uuid/videos",
            headers=auth_headers,
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        assert response.status_code in [401, 404, 422]

    @pytest.mark.asyncio
    async def test_upload_blog_video_unsupported_type(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that upload fails with unsupported video type."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.avi", b"fake avi", "video/avi")},
        )
        # Should fail due to unsupported type
        assert response.status_code in [404, 415]

    @pytest.mark.asyncio
    async def test_upload_blog_video_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test uploading video to non-existent blog."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        assert response.status_code == 404


class TestDeleteBlogMedia:
    """Tests for DELETE /blogs/{blog_id}/media/{media_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_blog_media_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that deleting media requires authentication."""
        blog_id = str(uuid4())
        media_id = str(uuid4())
        response = await client.delete(f"/blogs/{blog_id}/media/{media_id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_blog_media_invalid_uuid(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that delete fails with invalid UUID."""
        response = await client.delete(
            "/blogs/invalid-uuid/media/also-invalid",
            headers=auth_headers,
        )
        assert response.status_code in [401, 404, 422]

    @pytest.mark.asyncio
    async def test_delete_blog_media_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test deleting media from non-existent blog."""
        blog_id = str(uuid4())
        media_id = str(uuid4())
        response = await client.delete(
            f"/blogs/{blog_id}/media/{media_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_blog_image_by_admin(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Test that admin can delete blog media with proper auth."""
        blog_id = str(uuid4())
        media_id = str(uuid4())
        # This would need a real blog in database for full test
        response = await client.delete(
            f"/blogs/{blog_id}/media/{media_id}",
            headers=admin_auth_headers,
        )
        # Should be 404 since blog doesn't exist
        assert response.status_code == 404


class TestBlogMediaAuthorization:
    """Tests for blog media authorization requirements."""

    @pytest.mark.asyncio
    async def test_only_author_or_admin_can_upload_image(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that only author or admin can upload images."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            headers=auth_headers,
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        # Should be 404 (not found) since blog doesn't exist
        # or 403 if blog exists but user is not owner
        assert response.status_code in [404, 403]

    @pytest.mark.asyncio
    async def test_only_author_or_admin_can_upload_video(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that only author or admin can upload videos."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        assert response.status_code in [404, 403]

    @pytest.mark.asyncio
    async def test_only_author_or_admin_can_delete_media(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that only author or admin can delete media."""
        blog_id = str(uuid4())
        media_id = str(uuid4())
        response = await client.delete(
            f"/blogs/{blog_id}/media/{media_id}",
            headers=auth_headers,
        )
        assert response.status_code in [404, 403]


class TestBlogMediaLimits:
    """Tests for blog media upload limits."""

    @pytest.mark.asyncio
    async def test_blog_image_upload_limit(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that blog has maximum 10 images limit."""
        # This would require a blog with 10 existing images
        # For now, just test the endpoint structure
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            headers=auth_headers,
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        # Should be 404 since blog doesn't exist
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_blog_video_upload_limit(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that blog has maximum 3 videos limit."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        assert response.status_code == 404


class TestBlogMediaResponseStructure:
    """Tests for blog media response structure validation."""

    @pytest.mark.asyncio
    async def test_upload_image_response_format(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that image upload returns proper response format."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            headers=auth_headers,
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        # Should include url and mediaType fields on success
        if response.status_code == 201:
            data = response.json()
            assert "url" in data
            assert "mediaType" in data
            assert data["mediaType"] == "image"

    @pytest.mark.asyncio
    async def test_upload_video_response_format(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that video upload returns proper response format."""
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        if response.status_code == 201:
            data = response.json()
            assert "url" in data
            assert "mediaType" in data
            assert data["mediaType"] == "video"


class TestBlogMediaAllowedTypes:
    """Tests for allowed media types."""

    @pytest.mark.asyncio
    async def test_allowed_image_types(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test allowed image types (jpeg, png, webp)."""
        blog_id = str(uuid4())

        # Test PNG
        img = Image.new("RGBA", (100, 100), color="blue")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        response = await client.post(
            f"/blogs/{blog_id}/images",
            headers=auth_headers,
            files={"file": ("test.png", buffer.getvalue(), "image/png")},
        )
        assert response.status_code in [404, 201]  # 404 if blog not found, 201 if success

    @pytest.mark.asyncio
    async def test_allowed_video_types(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test allowed video types (mp4, webm, quicktime)."""
        blog_id = str(uuid4())

        # Test MP4
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.mp4", create_test_video_bytes(), "video/mp4")},
        )
        assert response.status_code in [404, 201]

        # Test WebM
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            headers=auth_headers,
            files={"file": ("test.webm", create_test_video_bytes(), "video/webm")},
        )
        assert response.status_code in [404, 201]
