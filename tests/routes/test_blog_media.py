"""Tests for blog media endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestUploadBlogImage:
    """Tests for POST /blogs/{blog_id}/images."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient) -> None:
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/images",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/blogs/invalid-uuid/images",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code in [401, 422]


class TestUploadBlogVideo:
    """Tests for POST /blogs/{blog_id}/videos."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient) -> None:
        blog_id = str(uuid4())
        response = await client.post(
            f"/blogs/{blog_id}/videos",
            files={"file": ("test.mp4", b"fake", "video/mp4")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/blogs/invalid-uuid/videos",
            files={"file": ("test.mp4", b"fake", "video/mp4")},
        )
        assert response.status_code in [401, 422]


class TestDeleteBlogMedia:
    """Tests for DELETE /blogs/{blog_id}/media/{media_id}."""

    @pytest.mark.asyncio
    async def test_delete_requires_authentication(self, client: AsyncClient) -> None:
        blog_id = str(uuid4())
        response = await client.delete(f"/blogs/{blog_id}/media/media-1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.delete("/blogs/invalid-uuid/media/media-1")
        assert response.status_code in [401, 422]
