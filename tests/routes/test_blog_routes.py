"""Tests for core blog CRUD and listing endpoints."""

from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_blog_repository, get_current_user
from app.errors.database import DatabaseError, DuplicateEntryError
from app.main import app
from app.models import BlogDB, UserDB


def _make_blog(author_id: UUID, **updates: object) -> BlogDB:
    now = datetime.now(UTC).replace(microsecond=0)
    blog = BlogDB(
        id=uuid4(),
        author_id=author_id,
        title="Bali Packing Guide",
        slug="bali-packing-guide",
        summary="What to bring for your Bali trip.",
        content=(
            "Packing for Bali is easier when you prepare for beaches, temples, and tropical weather before you leave home. "
            "Lightweight clothing, modest outfits for temple visits, sunscreen, sandals, and a reusable bottle will make the trip much more comfortable. "
            "It also helps to bring insect repellent, a light rain jacket, basic medicine, and a small day bag so you are ready for long sightseeing days across the island."
        ),
        view_count=3,
        word_count=120,
        reading_time_minutes=2,
        status="published",
        tags=["bali", "travel"],
        images_url=[],
        videos_url=[],
        created_at=now,
        updated_at=now,
    )
    return blog.model_copy(update=updates)


@pytest.fixture
def override_blog_dependencies(sample_user: UserDB) -> Generator[MagicMock]:
    original_overrides = app.dependency_overrides.copy()
    had_cache_manager = hasattr(app.state, "cache_manager")
    original_cache_manager = getattr(app.state, "cache_manager", None)

    mock_repo = MagicMock()
    mock_repo.create = AsyncMock()
    mock_repo.increment_view_count = AsyncMock()
    mock_repo.get_by_slug = AsyncMock()
    mock_repo.get_all = AsyncMock(return_value=[])
    mock_repo.get_by_author = AsyncMock(return_value=[])
    mock_repo.search_by_tags = AsyncMock(return_value=[])
    mock_repo.get_by_id = AsyncMock()
    mock_repo.update = AsyncMock()
    mock_repo.delete = AsyncMock(return_value=True)

    app.state.cache_manager = MagicMock()
    app.state.cache_manager.get = AsyncMock(return_value=None)
    app.state.cache_manager.set = AsyncMock()
    app.state.cache_manager.delete = AsyncMock()
    app.dependency_overrides[get_blog_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: sample_user

    yield mock_repo

    app.dependency_overrides = original_overrides
    if had_cache_manager:
        app.state.cache_manager = original_cache_manager
    elif hasattr(app.state, "cache_manager"):
        delattr(app.state, "cache_manager")


@pytest.mark.asyncio
async def test_create_blog_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    created_blog = _make_blog(sample_user.uuid)
    override_blog_dependencies.create.return_value = created_blog

    response = await client.post(
        "/blogs/create",
        json={
            "authorId": str(sample_user.uuid),
            "title": "Bali Packing Guide",
            "slug": "bali-packing-guide",
            "summary": "What to bring for your Bali trip.",
            "content": created_blog.content,
            "tags": ["bali", "travel"],
        },
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 201, response.text
    assert response.json()["authorId"] == str(sample_user.uuid)
    assert response.json()["slug"] == "bali-packing-guide"
    override_blog_dependencies.create.assert_awaited_once()
    assert override_blog_dependencies.create.call_args.args[0].title == "Bali Packing Guide"
    assert override_blog_dependencies.create.call_args.args[0].author_id == sample_user.uuid


@pytest.mark.asyncio
async def test_create_blog_returns_conflict_for_duplicate_slug(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.create.side_effect = DuplicateEntryError("Slug already exists")

    response = await client.post(
        "/blogs/create",
        json={
            "authorId": str(sample_user.uuid),
            "title": "Duplicate Blog",
            "slug": "duplicate-blog",
            "content": _make_blog(sample_user.uuid).content,
            "tags": ["bali"],
        },
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Slug already exists"


@pytest.mark.asyncio
async def test_create_blog_returns_bad_request_for_database_error(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.create.side_effect = DatabaseError("insert failed", status_code=400)

    response = await client.post(
        "/blogs/create",
        json={
            "authorId": str(sample_user.uuid),
            "title": "Broken Blog",
            "slug": "broken-blog",
            "content": _make_blog(sample_user.uuid).content,
            "tags": ["bali"],
        },
        headers={**auth_headers, "Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "insert failed"


@pytest.mark.asyncio
async def test_create_blog_returns_bad_request_for_invalid_response_model(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.create.return_value = _make_blog(sample_user.uuid)

    with patch(
        "app.routes.blog._validate_blog_response",
        side_effect=ValueError("invalid blog response"),
    ):
        response = await client.post(
            "/blogs/create",
            json={
                "authorId": str(sample_user.uuid),
                "title": "Bad Response Blog",
                "slug": "bad-response-blog",
                "content": _make_blog(sample_user.uuid).content,
                "tags": ["bali"],
            },
            headers={**auth_headers, "Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid blog response"


@pytest.mark.asyncio
async def test_get_blog_returns_not_found_when_missing(
    client: AsyncClient,
    override_blog_dependencies: MagicMock,
) -> None:
    blog_id = uuid4()
    override_blog_dependencies.increment_view_count.return_value = None

    response = await client.get(f"/blogs/by-id/{blog_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Blog with id '{blog_id}' not found"


@pytest.mark.asyncio
async def test_get_blog_by_slug_success(
    client: AsyncClient,
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.get_by_slug.return_value = _make_blog(sample_user.uuid)

    response = await client.get("/blogs/by-slug/bali-packing-guide")

    assert response.status_code == 200
    assert response.json()["slug"] == "bali-packing-guide"
    override_blog_dependencies.get_by_slug.assert_awaited_once_with("bali-packing-guide")


@pytest.mark.asyncio
async def test_get_blog_by_slug_returns_not_found_when_missing(
    client: AsyncClient,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.get_by_slug.return_value = None

    response = await client.get("/blogs/by-slug/missing-blog")

    assert response.status_code == 404
    assert response.json()["detail"] == "Blog with slug 'missing-blog' not found"


@pytest.mark.asyncio
async def test_get_blogs_uses_filters(
    client: AsyncClient,
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.get_all.return_value = [_make_blog(sample_user.uuid)]

    response = await client.get(
        f"/blogs/all?skip=1&limit=2&status=published&author_id={sample_user.uuid}",
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    override_blog_dependencies.get_all.assert_awaited_once_with(
        skip=1,
        limit=2,
        status="published",
        author_id=sample_user.uuid,
    )


@pytest.mark.asyncio
async def test_get_blogs_by_author_uses_pagination(
    client: AsyncClient,
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.get_by_author.return_value = [_make_blog(sample_user.uuid)]

    response = await client.get(f"/blogs/by-author-id/{sample_user.uuid}?skip=3&limit=4")

    assert response.status_code == 200
    override_blog_dependencies.get_by_author.assert_awaited_once_with(
        sample_user.uuid,
        skip=3,
        limit=4,
    )


@pytest.mark.asyncio
async def test_search_blogs_by_tags_uses_pagination(
    client: AsyncClient,
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    override_blog_dependencies.search_by_tags.return_value = [_make_blog(sample_user.uuid)]

    response = await client.get("/blogs/search/tags?tags=bali&tags=travel&skip=2&limit=5")

    assert response.status_code == 200
    override_blog_dependencies.search_by_tags.assert_awaited_once_with(
        ["bali", "travel"],
        skip=2,
        limit=5,
    )


@pytest.mark.asyncio
async def test_update_blog_returns_not_found_when_repo_update_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    blog_id = uuid4()
    override_blog_dependencies.get_by_id.return_value = _make_blog(sample_user.uuid, id=blog_id)
    override_blog_dependencies.update.return_value = None

    with patch(
        "app.routes.blog.delete_cache_keys",
        new_callable=AsyncMock,
    ) as mock_delete_cache_keys:
        response = await client.patch(
            f"/blogs/update/{blog_id}",
            json={"summary": "Updated summary"},
            headers=auth_headers,
        )

    assert response.status_code == 404
    assert response.json()["detail"] == f"Blog with id '{blog_id}' not found"
    mock_delete_cache_keys.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_blog_success_invalidates_cache(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    blog_id = uuid4()
    existing_blog = _make_blog(sample_user.uuid, id=blog_id, slug="old-slug")
    updated_blog = _make_blog(
        sample_user.uuid,
        id=blog_id,
        slug="new-slug",
        summary="Updated summary",
    )
    override_blog_dependencies.get_by_id.return_value = existing_blog
    override_blog_dependencies.update.return_value = updated_blog

    with patch(
        "app.routes.blog.delete_cache_keys",
        new_callable=AsyncMock,
    ) as mock_delete_cache_keys:
        response = await client.patch(
            f"/blogs/update/{blog_id}",
            json={"slug": "new-slug", "summary": "Updated summary"},
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    assert response.json()["slug"] == "new-slug"
    override_blog_dependencies.update.assert_awaited_once()
    assert mock_delete_cache_keys.await_count == 1
    await_args = mock_delete_cache_keys.await_args
    assert await_args is not None
    cache_args = await_args.args
    assert cache_args[0] == existing_blog
    assert cache_args[1] == updated_blog
    assert cache_args[2].url.path == f"/blogs/update/{blog_id}"


@pytest.mark.asyncio
async def test_delete_blog_still_succeeds_when_media_cleanup_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    blog_id = uuid4()
    existing_blog = _make_blog(
        sample_user.uuid,
        id=blog_id,
        images_url=["https://example.com/blog_images/cover.jpg"],
        videos_url=["https://example.com/blog_videos/clip.mp4"],
    )
    override_blog_dependencies.get_by_id.return_value = existing_blog

    with patch("app.routes.blog.MediaService") as mock_media_service:
        mock_instance = AsyncMock()
        mock_instance.delete_all_media.side_effect = RuntimeError("storage unavailable")
        mock_media_service.return_value = mock_instance

        response = await client.delete(f"/blogs/delete/{blog_id}", headers=auth_headers)

    assert response.status_code == 204
    override_blog_dependencies.delete.assert_awaited_once_with(blog_id)
    mock_instance.delete_all_media.assert_awaited_once_with("blog_images", str(blog_id))


@pytest.mark.asyncio
async def test_delete_blog_cleans_up_images_and_videos_and_busts_cache(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    blog_id = uuid4()
    existing_blog = _make_blog(
        sample_user.uuid,
        id=blog_id,
        images_url=["https://example.com/blog_images/media-1.jpg"],
        videos_url=["https://example.com/blog_videos/media-2.mp4"],
    )
    override_blog_dependencies.get_by_id.return_value = existing_blog

    with (
        patch("app.routes.blog.MediaService") as mock_media_service,
        patch(
            "app.routes.blog.delete_cache_keys",
            new_callable=AsyncMock,
        ) as mock_delete_cache_keys,
    ):
        mock_instance = AsyncMock()
        mock_media_service.return_value = mock_instance

        response = await client.delete(f"/blogs/delete/{blog_id}", headers=auth_headers)

    assert response.status_code == 204
    assert mock_instance.delete_all_media.await_args_list == [
        call("blog_images", str(blog_id)),
        call("blog_videos", str(blog_id)),
    ]
    override_blog_dependencies.delete.assert_awaited_once_with(blog_id)
    assert mock_delete_cache_keys.await_count == 1
    await_args = mock_delete_cache_keys.await_args
    assert await_args is not None
    cache_args = await_args.args
    assert cache_args[0] == existing_blog
    assert cache_args[1] is None
    assert cache_args[2].url.path == f"/blogs/delete/{blog_id}"


@pytest.mark.asyncio
async def test_delete_blog_returns_not_found_when_repo_delete_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_blog_dependencies: MagicMock,
) -> None:
    blog_id = uuid4()
    existing_blog = _make_blog(sample_user.uuid, id=blog_id)
    override_blog_dependencies.get_by_id.return_value = existing_blog
    override_blog_dependencies.delete.return_value = False

    with patch(
        "app.routes.blog.delete_cache_keys",
        new_callable=AsyncMock,
    ) as mock_delete_cache_keys:
        response = await client.delete(f"/blogs/delete/{blog_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == f"Blog with id '{blog_id}' not found"
    mock_delete_cache_keys.assert_not_awaited()
