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
from starlette.responses import Response
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
    "/create",
    response_class=ORJSONResponse,
    response_model=ReviewResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new review",
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "userId": "123e4567-e89b-12d3-a456-426614174000",
                        "itemId": None,
                        "rating": 5,
                        "comment": "Great product!",
                        "imagesUrl": [],
                        "createdAt": "2022-01-01T00:00:00Z",
                        "updatedAt": "2022-01-01T00:00:00Z",
                    },
                },
            },
        },
        400: {"content": {"application/json": {"example": {"detail": "Invalid request data"}}}},
        401: {"content": {"application/json": {"example": {"detail": "Not authenticated"}}}},
        403: {"content": {"application/json": {"example": {"detail": "Not authorized"}}}},
        404: {"content": {"application/json": {"example": {"detail": "Review not found"}}}},
        429: {"content": {"application/json": {"example": {"detail": "Too many requests"}}}},
        500: {"content": {"application/json": {"example": {"detail": "Internal server error"}}}},
    },
    operation_id="reviews_create",
)
@limiter.limit("10/minute")
async def create_review(
    request: Request,
    response: Response,
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
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "userId": "123e4567-e89b-12d3-a456-426614174000",
                        "itemId": None,
                        "rating": 5,
                        "comment": "Great product!",
                        "imagesUrl": [],
                        "createdAt": "2022-01-01T00:00:00Z",
                        "updatedAt": "2022-01-01T00:00:00Z",
                    },
                },
            },
        },
        404: {"content": {"application/json": {"example": {"detail": "Review not found"}}}},
        429: {"content": {"application/json": {"example": {"detail": "Too many requests"}}}},
        500: {"content": {"application/json": {"example": {"detail": "Internal server error"}}}},
    },
    operation_id="reviews_get",
)
@limiter.limit("60/minute")
async def get_review(
    request: Request,
    response: Response,
    review_id: UUID,
    repo: ReviewRepoDep,
) -> ReviewResponse:
    """Get a review by ID."""
    db_review = await repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    return _to_review_response(db_review)


@dataclass(frozen=True)
class ReviewListQuery:
    item_id: Annotated[UUID | None, Query(description="Filter by item ID")] = None
    skip: Annotated[int, Query(ge=0)] = 0
    limit: Annotated[int, Query(ge=1, le=100)] = 10


@router.get(
    "/list",
    response_class=ORJSONResponse,
    summary="List reviews",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "userId": "123e4567-e89b-12d3-a456-426614174000",
                            "itemId": None,
                            "rating": 5,
                            "comment": "Great product!",
                            "imagesUrl": [],
                            "createdAt": "2022-01-01T00:00:00Z",
                            "updatedAt": "2022-01-01T00:00:00Z",
                        },
                    ],
                },
            },
        },
        404: {"content": {"application/json": {"example": {"detail": "Review not found"}}}},
        429: {"content": {"application/json": {"example": {"detail": "Too many requests"}}}},
        500: {"content": {"application/json": {"example": {"detail": "Internal server error"}}}},
    },
    operation_id="reviews_list",
)
@limiter.limit("30/minute")
async def list_reviews(
    request: Request,
    response: Response,
    repo: ReviewRepoDep,
    deps: ReviewListQuery,
) -> list[ReviewListResponse]:
    """List reviews with optional item filter."""
    if deps.item_id:
        reviews = await repo.get_by_item(deps.item_id, skip=deps.skip, limit=deps.limit)
    else:
        reviews = await repo.get_all(skip=deps.skip, limit=deps.limit)

    return [_to_review_list_response(r) for r in reviews]


@router.patch(
    "/update/{review_id}",
    response_class=ORJSONResponse,
    summary="Update a review",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "userId": "123e4567-e89b-12d3-a456-426614174000",
                        "itemId": None,
                        "rating": 5,
                        "comment": "Great product!",
                        "imagesUrl": [],
                        "createdAt": "2022-01-01T00:00:00Z",
                        "updatedAt": "2022-01-01T00:00:00Z",
                    },
                },
            },
        },
        404: {"content": {"application/json": {"example": {"detail": "Review not found"}}}},
        429: {"content": {"application/json": {"example": {"detail": "Too many requests"}}}},
        500: {"content": {"application/json": {"example": {"detail": "Internal server error"}}}},
    },
    operation_id="reviews_update",
)
@limiter.limit("10/minute")
async def update_review(
    request: Request,
    response: Response,
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
    "/delete/{review_id}",
    status_code=HTTP_204_NO_CONTENT,
    response_class=ORJSONResponse,
    summary="Delete a review",
    responses={
        204: {
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Review deleted successfully",
                    },
                },
            },
        },
        404: {
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Review not found",
                    },
                },
            },
        },
        429: {
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Too many requests",
                    },
                },
            },
        },
        500: {
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Internal server error",
                    },
                },
            },
        },
    },
    operation_id="reviews_delete",
)
@limiter.limit("5/minute")
async def delete_review(
    request: Request,
    response: Response,
    review_id: UUID,
    deps: ReviewOpsDep,
) -> Response:
    """Delete a review (owner or admin only)."""
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    # [NEW] Cleanup all associated media
    if db_review.images_url:
        media_service = MediaService()
        try:
            await media_service.delete_all_media("review_images", str(review_id))
        except Exception:
            logger.exception("Failed to cleanup media for review %s during deletion", review_id)

    if not await deps.repo.delete(review_id):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    return Response(status_code=HTTP_204_NO_CONTENT)


@router.post(
    "/upload-images/{review_id}",
    response_class=ORJSONResponse,
    status_code=HTTP_201_CREATED,
    summary="Upload an image to a review",
)
@limiter.limit("10/minute")
async def upload_review_image(
    request: Request,
    response: Response,
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
        media_id, url = await media_service.upload_review_image(
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

    return MediaUploadResponse(mediaId=media_id, url=url, mediaType="image")


@router.delete(
    "/delete-images/{review_id}/{media_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete an image from a review",
    response_class=ORJSONResponse,
)
@limiter.limit("10/minute")
async def delete_review_image(
    request: Request,
    response: Response,
    review_id: UUID,
    media_id: str,
    deps: ReviewOpsDep,
) -> Response:
    """Delete an image from a review (owner or admin only)."""
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    if not db_review.images_url or not any(f"/{media_id}" in url for url in db_review.images_url):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")

    media_service = MediaService()
    deleted = await media_service.delete_media(
        folder="review_images",
        entity_id=str(review_id),
        media_id=media_id,
    )
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")

    removed = await deps.repo.remove_image_by_media_id(review_id, media_id)
    if not removed:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")

    return Response(status_code=HTTP_204_NO_CONTENT)
