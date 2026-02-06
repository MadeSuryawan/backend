"""Tests for review media endpoints."""

from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestUploadReviewImage:
    """Tests for POST /reviews/{review_id}/images."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(self, client: AsyncClient) -> None:
        review_id = str(uuid4())
        response = await client.post(
            f"/reviews/upload-images/{review_id}",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/reviews/upload-images/invalid-uuid",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code in [401, 422]


class TestDeleteReviewImage:
    """Tests for DELETE /reviews/{review_id}/images/{media_id}."""

    @pytest.mark.asyncio
    async def test_delete_requires_authentication(self, client: AsyncClient) -> None:
        review_id = str(uuid4())
        response = await client.delete(f"/reviews/delete-images/{review_id}/media-1")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(self, client: AsyncClient) -> None:
        response = await client.delete("/reviews/delete-images/invalid-uuid/media-1")
        assert response.status_code in [401, 422]
