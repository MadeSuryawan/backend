# tests/routes/test_profile_picture.py
"""
Tests for profile picture API endpoints.

These tests verify the authentication requirements for profile picture endpoints.
More comprehensive integration tests would require a full database setup.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestUploadProfilePicture:
    """Tests for POST /{user_id}/profile-picture endpoint."""

    @pytest.mark.asyncio
    async def test_upload_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload requires authentication."""
        user_id = str(uuid4())
        response = await client.post(
            f"/users/{user_id}/profile-picture",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_invalid_uuid(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that upload fails with invalid UUID."""
        response = await client.post(
            "/users/invalid-uuid/profile-picture",
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
        )
        # Should be 401 (unauthenticated) or 422 (validation error)
        assert response.status_code in [401, 422]


class TestDeleteProfilePicture:
    """Tests for DELETE /{user_id}/profile-picture endpoint."""

    @pytest.mark.asyncio
    async def test_delete_requires_authentication(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that delete requires authentication."""
        user_id = str(uuid4())
        response = await client.delete(f"/users/{user_id}/profile-picture")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid(
        self,
        client: AsyncClient,
    ) -> None:
        """Test that delete fails with invalid UUID."""
        response = await client.delete("/users/invalid-uuid/profile-picture")
        # Should be 401 (unauthenticated) or 422 (validation error)
        assert response.status_code in [401, 422]
