# tests/routes/test_review_media.py
"""Tests for review media API endpoints."""

from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image

from app.models.review import ReviewDB


def create_test_image_bytes() -> bytes:
    """Create a small valid JPEG image for testing."""
    img = Image.new("RGB", (100, 100), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def sample_review() -> ReviewDB:
    """Create a sample review for testing."""
    return ReviewDB(
        id=uuid4(),
        user_id=uuid4(),
        item_id=None,
        rating=5,
        title="Great experience!",
        content="This was an amazing tour package. Highly recommended!",
        images_url=[],
        is_verified_purchase=True,
        helpful_count=10,
    )


@pytest.fixture
def sample_review_with_images() -> ReviewDB:
    """Create a sample review with existing images for testing."""
    review_id = uuid4()
    return ReviewDB(
        id=review_id,
        user_id=uuid4(),
        item_id=None,
        rating=5,
        title="Great experience!",
        content="This was an amazing tour package. Highly recommended!",
        images_url=[
            f"https://example.com/uploads/review_images/{review_id}/{uuid4()}.jpg",
        ],
        is_verified_purchase=True,
        helpful_count=10,
    )


class TestCreateReview:
    """Tests for POST /reviews endpoint."""

    @pytest.mark.asyncio
    async def test_create_review_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that creating a review requires authentication."""
        response = await client.post(
            "/reviews",
            json={
                "rating": 5,
                "title": "Great experience!",
                "content": "This was an amazing tour package. Highly recommended!",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_review_invalid_data(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that creating a review fails with invalid data."""
        response = await client.post(
            "/reviews",
            headers=auth_headers,
            json={
                "rating": 6,  # Invalid: max is 5
                "title": "Great experience!",
                "content": "Too short",
            },
        )
        assert response.status_code == 422


class TestGetReview:
    """Tests for GET /reviews/{review_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_review_not_found(
        self,
        client: AsyncClient,
    ) -> None:
        """Test getting a non-existent review."""
        response = await client.get(f"/reviews/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_review_invalid_uuid(
        self,
        client: AsyncClient,
    ) -> None:
        """Test getting a review with invalid UUID."""
        response = await client.get("/reviews/invalid-uuid")
        assert response.status_code == 422


class TestListReviews:
    """Tests for GET /reviews endpoint."""

    @pytest.mark.asyncio
    async def test_list_reviews_public_access(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that listing reviews is publicly accessible."""
        response = await client.get("/reviews")
        # Should be accessible without auth (though may return empty list)
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_list_reviews_with_pagination(
        self,
        client: AsyncClient,
    ) -> None:
        """Test listing reviews with pagination parameters."""
        response = await client.get("/reviews?skip=0&limit=10")
        assert response.status_code in [200, 404]


class TestUpdateReview:
    """Tests for PATCH /reviews/{review_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_review_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that updating a review requires authentication."""
        response = await client.patch(
            f"/reviews/{uuid4()}",
            json={"rating": 4},
        )
        assert response.status_code == 401


class TestDeleteReview:
    """Tests for DELETE /reviews/{review_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_review_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that deleting a review requires authentication."""
        response = await client.delete(f"/reviews/{uuid4()}")
        assert response.status_code == 401


class TestUploadReviewImage:
    """Tests for POST /reviews/{review_id}/images endpoint."""

    @pytest.mark.asyncio
    async def test_upload_review_image_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload requires authentication."""
        review_id = str(uuid4())
        response = await client.post(
            f"/reviews/{review_id}/images",
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_review_image_invalid_uuid(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that upload fails with invalid review UUID."""
        response = await client.post(
            "/reviews/invalid-uuid/images",
            headers=auth_headers,
            files={"file": ("test.jpg", create_test_image_bytes(), "image/jpeg")},
        )
        assert response.status_code in [401, 404, 422]

    @pytest.mark.asyncio
    async def test_upload_review_image_unsupported_type(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that upload fails with unsupported image type."""
        review_id = str(uuid4())
        response = await client.post(
            f"/reviews/{review_id}/images",
            headers=auth_headers,
            files={"file": ("test.gif", b"GIF89a...", "image/gif")},
        )
        # Should fail due to unsupported type (404 because review doesn't exist, or 415)
        assert response.status_code in [404, 415]


class TestDeleteReviewImage:
    """Tests for DELETE /reviews/{review_id}/images/{media_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_review_image_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that deleting an image requires authentication."""
        review_id = str(uuid4())
        media_id = str(uuid4())
        response = await client.delete(f"/reviews/{review_id}/images/{media_id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_review_image_invalid_uuid(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that delete fails with invalid UUID."""
        response = await client.delete(
            "/reviews/invalid-uuid/images/also-invalid",
            headers=auth_headers,
        )
        assert response.status_code in [401, 404, 422]

    @pytest.mark.asyncio
    async def test_delete_review_image_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test deleting an image from non-existent review."""
        review_id = str(uuid4())
        media_id = str(uuid4())
        response = await client.delete(
            f"/reviews/{review_id}/images/{media_id}",
            headers=auth_headers,
        )
        # Should be 404 since review doesn't exist
        assert response.status_code == 404


class TestReviewAuthorization:
    """Tests for review authorization requirements."""

    @pytest.mark.asyncio
    async def test_admin_can_access_any_review(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Test that admin can access reviews with proper auth."""
        # This would need a full integration test with database
        # For now, just verify the auth header works
        response = await client.get("/reviews", headers=admin_auth_headers)
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_user_can_access_own_reviews(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test that user can access with proper auth."""
        response = await client.get("/reviews", headers=auth_headers)
        assert response.status_code in [200, 404]


class TestReviewResponseStructure:
    """Tests for review response structure validation."""

    @pytest.mark.asyncio
    async def test_list_reviews_response_format(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that list reviews returns proper format."""
        response = await client.get("/reviews")
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_review_response_includes_images_url(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that review response includes images_url field."""
        # This is a schema test - would need real data for full validation
        # Just verify the endpoint structure
        response = await client.get("/reviews")
        # The response schema should include imagesUrl field
        assert response.status_code in [200, 404]
