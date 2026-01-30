"""
Review Routes.

Provides CRUD endpoints for user reviews with media upload support.
"""

from dataclasses import dataclass
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import ORJSONResponse
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)

from app.auth.permissions import check_owner_or_admin
from app.dependencies import ReviewRepoDep, UserDBDep
from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
)
from app.managers.rate_limiter import limiter
from app.models.review import ReviewDB
from app.schemas.review import (
    MediaUploadResponse,
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
    ReviewUpdate,
)
from app.services import MediaService
from app.utils.helpers import file_logger, response_datetime

router = APIRouter(prefix="/reviews", tags=["⭐ Reviews"])

logger = file_logger(getLogger(__name__))


@dataclass(frozen=True)
class ReviewOpsDeps:
    """Dependencies for authenticated review operations."""

    repo: ReviewRepoDep
    current_user: UserDBDep


def get_review_ops_deps(
    repo: ReviewRepoDep,
    current_user: UserDBDep,
) -> ReviewOpsDeps:
    """Get review operation dependencies."""
    return ReviewOpsDeps(repo=repo, current_user=current_user)


ReviewOpsDep = Annotated[ReviewOpsDeps, Depends(get_review_ops_deps)]


def _to_review_response(db_review: "ReviewDB") -> ReviewResponse:
    """Convert ReviewDB to ReviewResponse with formatted datetimes."""
    review_dict = response_datetime(db_review)
    return ReviewResponse.model_validate(review_dict)


def _to_review_list_response(db_review: "ReviewDB") -> ReviewListResponse:
    """Convert ReviewDB to ReviewListResponse with formatted datetimes."""
    review_dict = response_datetime(db_review)
    return ReviewListResponse.model_validate(review_dict)


@router.post(
    "",
    response_class=ORJSONResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new review",
)
@limiter.limit("10/minute")
async def create_review(
    request: Request,
    review_data: ReviewCreate,
    deps: ReviewOpsDep,
) -> ReviewResponse:
    """Create a new review."""
    db_review = await deps.repo.create(review_data, deps.current_user.uuid)
    return _to_review_response(db_review)


@router.get(
    "/{review_id}",
    response_class=ORJSONResponse,
    summary="Get a review by ID",
)
@limiter.limit("60/minute")
async def get_review(
    request: Request,
    review_id: UUID,
    repo: ReviewRepoDep,
) -> ReviewResponse:
    """Get a review by ID."""
    db_review = await repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    return _to_review_response(db_review)


@router.get(
    "",
    response_class=ORJSONResponse,
    summary="List reviews",
)
@limiter.limit("30/minute")
async def list_reviews(
    request: Request,
    repo: ReviewRepoDep,
    item_id: Annotated[UUID | None, Query(description="Filter by item ID")] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[ReviewListResponse]:
    """List reviews with optional item filter."""
    if item_id:
        reviews = await repo.get_by_item(item_id, skip=skip, limit=limit)
    else:
        reviews = await repo.get_all(skip=skip, limit=limit)

    return [_to_review_list_response(r) for r in reviews]


@router.patch(
    "/{review_id}",
    response_class=ORJSONResponse,
    summary="Update a review",
)
@limiter.limit("10/minute")
async def update_review(
    request: Request,
    review_id: UUID,
    review_data: ReviewUpdate,
    deps: ReviewOpsDep,
) -> ReviewResponse:
    """Update a review (owner only)."""
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    updated = await deps.repo.update(review_id, review_data)
    if not updated:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    return _to_review_response(updated)


@router.delete(
    "/{review_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete a review",
)
@limiter.limit("5/minute")
async def delete_review(
    request: Request,
    review_id: UUID,
    deps: ReviewOpsDep,
) -> None:
    """Delete a review (owner or admin only)."""
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)
    await deps.repo.delete(review_id)


@router.post(
    "/{review_id}/images",
    response_class=ORJSONResponse,
    status_code=HTTP_201_CREATED,
    summary="Upload an image to a review",
)
@limiter.limit("10/minute")
async def upload_review_image(
    request: Request,
    review_id: UUID,
    file: UploadFile,
    deps: ReviewOpsDep,
) -> MediaUploadResponse:
    """Upload an image to a review (owner only, max 5 images)."""
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    current_count = len(db_review.images_url) if db_review.images_url else 0
    media_service = MediaService()

    try:
        url = await media_service.upload_review_image(
            review_id=str(review_id),
            file=file,
            current_count=current_count,
        )
    except (
        UnsupportedImageTypeError,
        ImageTooLargeError,
        InvalidImageError,
        ImageProcessingError,
        MediaLimitExceededError,
    ) as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    await deps.repo.add_image(review_id, url)

    return MediaUploadResponse(url=url, mediaType="image")


@router.delete(
    "/{review_id}/images/{media_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete a review image",
)
@limiter.limit("10/minute")
async def delete_review_image(
    request: Request,
    review_id: UUID,
    media_id: str,
    deps: ReviewOpsDep,
) -> None:
    """Delete an image from a review (owner only)."""
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    media_service = MediaService()

    # Check if media exists in review images
    if not db_review.images_url or not any(media_id in str(url) for url in db_review.images_url):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Image not found in review")

    # Delete from storage
    await media_service.delete_media("review_images", str(review_id), media_id)

    # Remove from database
    await deps.repo.remove_image(review_id, media_id)
