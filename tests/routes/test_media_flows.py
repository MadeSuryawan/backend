from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT, HTTP_404_NOT_FOUND

from app.dependencies.dependencies import (
    get_blog_repository,
    get_current_user,
    get_review_repository,
)
from app.main import app
from app.models.blog import BlogDB
from app.models.review import ReviewDB
from app.models.user import UserDB
from app.routes.review import ReviewOpsDep


# Fixtures for data
@pytest.fixture
def test_user():
    return UserDB(
        uuid=uuid4(),
        email="test@example.com",
        username="testuser",
        is_active=True,
        is_verified=True,
        role="user",
        password_hash="hash",
    )


@pytest.fixture
def test_review(test_user):
    return ReviewDB(
        id=uuid4(),
        user_id=test_user.uuid,
        item_id=uuid4(),
        rating=5,
        title="Good",
        content="Good stuff",
        images_url=[],
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def test_blog(test_user):
    return BlogDB(
        id=uuid4(),
        author_id=test_user.uuid,
        title="Blog",
        slug="blog-slug",
        content="Content",
        summary="Summary",
        status="published",
        images_url=[],
        videos_url=[],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# Mocks
@pytest.fixture
def mock_review_repo(test_review):
    mock = MagicMock()
    mock.get_by_id = AsyncMock(return_value=test_review)
    mock.add_image = AsyncMock(return_value=test_review)
    mock.remove_image = AsyncMock(return_value=test_review)
    return mock


@pytest.fixture
def mock_blog_repo(test_blog):
    mock = MagicMock()
    mock.get_by_id = AsyncMock(return_value=test_blog)
    mock.add_image = AsyncMock(return_value=test_blog)
    mock.remove_image = AsyncMock(return_value=test_blog)
    mock.add_video = AsyncMock(return_value=test_blog)
    mock.remove_video = AsyncMock(return_value=test_blog)
    return mock


@pytest.fixture
def mock_media_service():
    mock = MagicMock()
    mock.upload_review_image = AsyncMock(
        return_value="http://res.cloudinary.com/demo/image/upload/v1/review_images/uuid/media_id.jpg"
    )
    mock.upload_blog_image = AsyncMock(
        return_value="http://res.cloudinary.com/demo/image/upload/v1/blog_images/uuid/media_id_img.jpg"
    )
    mock.upload_blog_video = AsyncMock(
        return_value="http://res.cloudinary.com/demo/video/upload/v1/blog_videos/uuid/media_id_vid.mp4"
    )
    mock.delete_media = AsyncMock(return_value=True)
    return mock


@pytest.mark.asyncio
async def test_review_image_upload_and_delete_flow(
    client: AsyncClient,
    test_user: UserDB,
    test_review: ReviewDB,
    mock_review_repo,
    mock_media_service,
):
    # Override dependencies
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_review_repository] = lambda: mock_review_repo

    # Patch MediaService
    with patch("app.routes.review.MediaService", return_value=mock_media_service):
        # 1. Upload
        files = {"file": ("image.jpg", b"fake-content", "image/jpeg")}
        # IMPORTANT: MediaService might validate bytes.
        # But we mocked MediaService.upload_review_image, so the actual validation inside MediaService won't run.
        # However, FastAPI might parse UploadFile.
        # Let's see if our mock bypasses the validation logic.

        response = await client.post(f"/reviews/{test_review.id}/images", files=files)
        assert response.status_code == HTTP_201_CREATED, response.text
        data = response.json()
        url = data["url"]
        assert (
            url == "http://res.cloudinary.com/demo/image/upload/v1/review_images/uuid/media_id.jpg"
        )
        media_id = "media_id"

        # Update test_review state to simulate DB change
        test_review.images_url = [url]

        # 2. Delete
        response = await client.delete(f"/reviews/{test_review.id}/images/{media_id}")
        assert response.status_code == HTTP_204_NO_CONTENT

        # Verify calls
        mock_media_service.delete_media.assert_called_with(
            "review_images", str(test_review.id), media_id
        )
        mock_review_repo.remove_image.assert_called_with(test_review.id, media_id)

    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_blog_media_upload_and_delete_flow(
    client: AsyncClient, test_user: UserDB, test_blog: BlogDB, mock_blog_repo, mock_media_service
):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_blog_repository] = lambda: mock_blog_repo

    with patch("app.routes.blog.MediaService", return_value=mock_media_service):
        # 1. Upload Image
        files = {"file": ("blog.jpg", b"fake", "image/jpeg")}
        response = await client.post(f"/blogs/{test_blog.id}/images", files=files)
        assert response.status_code == HTTP_201_CREATED
        url_img = response.json()["url"]
        media_id_img = "media_id_img"  # from our mock return

        # 2. Upload Video
        files = {"file": ("blog.mp4", b"fake", "video/mp4")}
        response = await client.post(f"/blogs/{test_blog.id}/videos", files=files)
        assert response.status_code == HTTP_201_CREATED
        url_vid = response.json()["url"]
        media_id_vid = "media_id_vid"

        # Update state
        test_blog.images_url = [url_img]
        test_blog.videos_url = [url_vid]

        # 3. Delete Image
        response = await client.delete(f"/blogs/{test_blog.id}/media/{media_id_img}")
        assert response.status_code == HTTP_204_NO_CONTENT
        mock_media_service.delete_media.assert_any_call(
            "blog_images", str(test_blog.id), media_id_img
        )
        mock_blog_repo.remove_image.assert_called_with(test_blog.id, media_id_img)

        # 4. Delete Video
        response = await client.delete(f"/blogs/{test_blog.id}/media/{media_id_vid}")
        assert response.status_code == HTTP_204_NO_CONTENT
        mock_media_service.delete_media.assert_any_call(
            "blog_videos", str(test_blog.id), media_id_vid
        )
        mock_blog_repo.remove_video.assert_called_with(test_blog.id, media_id_vid)

    app.dependency_overrides = {}
