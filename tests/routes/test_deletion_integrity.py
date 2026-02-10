from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.dependencies.dependencies import (
    get_blog_repository,
    get_current_user,
    get_review_repository,
    get_user_repository,
)
from app.main import app
from app.models.blog import BlogDB
from app.models.review import ReviewDB
from app.models.user import UserDB


@pytest.fixture(autouse=True)
def setup_teardown() -> Generator[None]:
    # Setup: Mock cache_manager on app.state
    app.state.cache_manager = MagicMock()
    app.state.cache_manager.delete = AsyncMock()
    app.state.cache_manager.clear = AsyncMock()

    yield

    # Teardown: Clear overrides
    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_delete_user_triggers_cleanup(client: AsyncClient) -> None:
    user_id = uuid4()
    mock_user = MagicMock(spec=UserDB)
    mock_user.uuid = user_id
    mock_user.username = "testuser"
    mock_user.profile_picture = "http://example.com/pic.jpg"
    mock_user.role = "user"
    mock_user.is_active = True

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = mock_user
    mock_repo.delete.return_value = True

    app.dependency_overrides[get_user_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with (
        patch("app.dependencies.dependencies.check_owner_or_admin", return_value=None),
        patch("app.routes.user._get_pp_service") as mock_pp_service,
        patch("app.routes.user._invalidate_user_cache", new_callable=AsyncMock),
    ):
        mock_pp_instance = AsyncMock()
        mock_pp_service.return_value = mock_pp_instance

        response = await client.delete(f"/users/delete/{user_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_pp_instance.delete_profile_picture.assert_called_once_with(str(user_id))
        mock_repo.delete.assert_called_once_with(user_id)


@pytest.mark.asyncio
async def test_delete_blog_triggers_cleanup(client: AsyncClient) -> None:
    blog_id = uuid4()
    author_id = uuid4()
    mock_blog = MagicMock(spec=BlogDB)
    mock_blog.id = blog_id
    mock_blog.author_id = author_id
    mock_blog.images_url = ["img1.jpg"]
    mock_blog.videos_url = ["vid1.mp4"]

    mock_user = MagicMock(spec=UserDB)
    mock_user.uuid = author_id
    mock_user.role = "user"
    mock_user.is_active = True

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = mock_blog
    mock_repo.delete.return_value = True

    app.dependency_overrides[get_blog_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with (
        patch("app.routes.blog.MediaService") as mock_media_service,
        patch("app.routes.blog.delete_cache_keys", new_callable=AsyncMock),
        patch("app.routes.blog.check_owner_or_admin", return_value=None),
    ):
        mock_media_instance = AsyncMock()
        mock_media_service.return_value = mock_media_instance

        response = await client.delete(f"/blogs/delete/{blog_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_media_instance.delete_all_media.assert_any_call("blog_images", str(blog_id))
        mock_media_instance.delete_all_media.assert_any_call("blog_videos", str(blog_id))


@pytest.mark.asyncio
async def test_delete_review_triggers_cleanup(client: AsyncClient) -> None:
    review_id = uuid4()
    user_id = uuid4()
    mock_review = MagicMock(spec=ReviewDB)
    mock_review.id = review_id
    mock_review.user_id = user_id
    mock_review.images_url = ["img.jpg"]

    mock_user = MagicMock(spec=UserDB)
    mock_user.uuid = user_id
    mock_user.role = "user"
    mock_user.is_active = True

    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = mock_review
    mock_repo.delete.return_value = True

    app.dependency_overrides[get_review_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: mock_user

    with (
        patch("app.routes.review.MediaService") as mock_media_service,
        patch("app.routes.review.check_owner_or_admin", return_value=None),
    ):
        mock_media_instance = AsyncMock()
        mock_media_service.return_value = mock_media_instance

        response = await client.delete(f"/reviews/delete/{review_id}")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_media_instance.delete_all_media.assert_called_once_with(
            "review_images",
            str(review_id),
        )
