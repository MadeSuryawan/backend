"""Tests for core review CRUD endpoints."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from app.dependencies.dependencies import get_current_user, get_review_repository
from app.main import app
from app.models import ReviewDB, UserDB
from app.routes.review import _validate_review_response
from app.schemas.review import ReviewResponse


def _make_review(user_id: UUID, item_id: UUID | None = None) -> ReviewDB:
    return ReviewDB(
        user_id=user_id,
        item_id=item_id,
        rating=5,
        title="Great trip",
        content="This was an amazing and well organized Bali experience.",
        images_url=["https://example.com/review.jpg"],
        is_verified_purchase=True,
        helpful_count=3,
    )


@pytest.fixture
def override_review_dependencies(sample_user: UserDB) -> Generator[MagicMock]:
    original_overrides = app.dependency_overrides.copy()

    mock_repo = MagicMock()
    mock_repo.create = AsyncMock()
    mock_repo.get_by_id = AsyncMock()
    mock_repo.get_all = AsyncMock(return_value=[])
    mock_repo.get_by_item = AsyncMock(return_value=[])
    mock_repo.update = AsyncMock()
    mock_repo.delete = AsyncMock(return_value=True)

    app.dependency_overrides[get_review_repository] = lambda: mock_repo
    app.dependency_overrides[get_current_user] = lambda: sample_user

    yield mock_repo

    app.dependency_overrides = original_overrides


@pytest.mark.asyncio
async def test_create_review_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    created_review = _make_review(sample_user.uuid)
    override_review_dependencies.create.return_value = created_review
    headers = {**auth_headers, "Idempotency-Key": str(uuid4())}

    payload = {"rating": 5, "title": "Great trip", "content": created_review.content}
    response = await client.post("/reviews/create", json=payload, headers=headers)

    assert response.status_code == 201, response.text
    assert response.json()["userId"] == str(sample_user.uuid)
    override_review_dependencies.create.assert_called_once()
    args = override_review_dependencies.create.call_args.args
    assert args[0].rating == 5
    assert args[1] == sample_user.uuid


@pytest.mark.asyncio
async def test_get_review_returns_not_found(
    client: AsyncClient,
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = None

    response = await client.get(f"/reviews/{review_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found"
    override_review_dependencies.get_by_id.assert_awaited_once_with(review_id)


@pytest.mark.asyncio
async def test_get_review_success(
    client: AsyncClient,
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    review = _make_review(sample_user.uuid)
    override_review_dependencies.get_by_id.return_value = review

    response = await client.get(f"/reviews/{review.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(review.id)
    assert response.json()["userId"] == str(sample_user.uuid)


@pytest.mark.asyncio
async def test_list_reviews_uses_item_filter(
    client: AsyncClient,
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    item_id = uuid4()
    override_review_dependencies.get_by_item.return_value = [
        _make_review(sample_user.uuid, item_id),
    ]

    response = await client.get(f"/reviews/list?item_id={item_id}&skip=1&limit=2")

    assert response.status_code == 200
    assert len(response.json()) == 1
    override_review_dependencies.get_by_item.assert_awaited_once_with(item_id, skip=1, limit=2)
    override_review_dependencies.get_all.assert_not_called()


@pytest.mark.asyncio
async def test_list_reviews_without_item_filter_uses_get_all(
    client: AsyncClient,
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    override_review_dependencies.get_all.return_value = [_make_review(sample_user.uuid)]

    response = await client.get("/reviews/list?skip=2&limit=3")

    assert response.status_code == 200
    assert len(response.json()) == 1
    override_review_dependencies.get_all.assert_awaited_once_with(skip=2, limit=3)
    override_review_dependencies.get_by_item.assert_not_called()


@pytest.mark.asyncio
async def test_update_review_forbidden_for_non_owner(
    client: AsyncClient,
    auth_headers: dict[str, str],
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = _make_review(uuid4())

    response = await client.patch(
        f"/reviews/update/{review_id}",
        json={"content": "Updated review text that is long enough."},
        headers=auth_headers,
    )

    assert response.status_code == 403
    override_review_dependencies.update.assert_not_called()


@pytest.mark.asyncio
async def test_update_review_returns_not_found_when_missing_before_update(
    client: AsyncClient,
    auth_headers: dict[str, str],
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = None

    response = await client.patch(
        f"/reviews/update/{review_id}",
        json={"content": "Updated review text that is long enough."},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found"
    override_review_dependencies.update.assert_not_called()


@pytest.mark.asyncio
async def test_update_review_returns_not_found_when_repo_update_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = _make_review(sample_user.uuid)
    override_review_dependencies.update.return_value = None

    response = await client.patch(
        f"/reviews/update/{review_id}",
        json={"content": "Updated review text that is long enough."},
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found"
    override_review_dependencies.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_review_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    existing_review = _make_review(sample_user.uuid)
    updated_review = existing_review.model_copy(
        update={"content": "Updated review text that is long enough."},
    )
    override_review_dependencies.get_by_id.return_value = existing_review
    override_review_dependencies.update.return_value = updated_review

    response = await client.patch(
        f"/reviews/update/{review_id}",
        json={"content": "Updated review text that is long enough."},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Updated review text that is long enough."
    override_review_dependencies.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_review_returns_not_found_when_missing(
    client: AsyncClient,
    auth_headers: dict[str, str],
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = None

    response = await client.delete(f"/reviews/delete/{review_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found"
    override_review_dependencies.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_review_returns_not_found_when_repo_delete_fails_after_lookup(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = _make_review(sample_user.uuid).model_copy(
        update={"images_url": None},
    )
    override_review_dependencies.delete.return_value = False

    response = await client.delete(f"/reviews/delete/{review_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Review not found"
    override_review_dependencies.delete.assert_awaited_once_with(review_id)


@pytest.mark.asyncio
async def test_delete_review_still_succeeds_when_media_cleanup_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    sample_user: UserDB,
    override_review_dependencies: MagicMock,
) -> None:
    review_id = uuid4()
    override_review_dependencies.get_by_id.return_value = _make_review(sample_user.uuid)

    with patch("app.routes.review.MediaService") as mock_media_service:
        mock_instance = AsyncMock()
        mock_instance.delete_all_media.side_effect = RuntimeError("storage unavailable")
        mock_media_service.return_value = mock_instance

        response = await client.delete(f"/reviews/delete/{review_id}", headers=auth_headers)

    assert response.status_code == 204
    override_review_dependencies.delete.assert_awaited_once_with(review_id)
    mock_instance.delete_all_media.assert_awaited_once_with("review_images", str(review_id))


def test_validate_review_response_raises_value_error_for_invalid_schema_data(
    sample_user: UserDB,
) -> None:
    invalid_review = _make_review(sample_user.uuid).model_copy(update={"images_url": ["not-a-url"]})

    with pytest.raises(ValueError, match="Validation error converting review to response model"):
        _validate_review_response(ReviewResponse, invalid_review)
