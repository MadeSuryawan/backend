"""
Review Routes.

Provides CRUD endpoints for user reviews with media upload support.
"""

from dataclasses import dataclass
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, ValidationError
from starlette.responses import Response
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)

from app.dependencies import ReviewRepoDep, UserDBDep, check_owner_or_admin
from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
)
from app.managers.rate_limiter import limiter
from app.models.review import ReviewDB
from app.monitoring import get_logger
from app.schemas.review import (
    MediaUploadResponse,
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
    ReviewUpdate,
)
from app.services import MediaService
from app.utils.helpers import response_datetime

router = APIRouter(prefix="/reviews", tags=["⭐ Reviews"])

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReviewOpsDeps:
    """
    Dependencies for authenticated review operations.

    Attributes
    ----------
    repo : ReviewRepoDep
        The review repository dependency.
    current_user : UserDBDep
        The current authenticated user dependency.
    """

    repo: ReviewRepoDep
    current_user: UserDBDep


@dataclass(frozen=True)
class ReviewListQuery:
    """
    Query parameters for listing reviews.

    Attributes
    ----------
    item_id : UUID | None
        Optional item ID to filter by.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    """

    item_id: Annotated[UUID | None, Query(description="Filter by item ID")] = None
    skip: Annotated[int, Query(ge=0)] = 0
    limit: Annotated[int, Query(ge=1, le=100)] = 10


def _validate_review_response(
    schema: type[BaseModel],
    review_dict: ReviewDB,
    user_timezone: str = "UTC",
) -> BaseModel:
    """
    Validate review response.

    Parameters
    ----------
    schema : type[BaseModel]
        The Pydantic model to validate against.
    review_dict : ReviewDB
        The database review object to validate.
    user_timezone : str
        IANA timezone string for datetime formatting.

    Returns
    -------
    BaseModel
        The validated Pydantic model.

    Raises
    ------
    ValueError
        If validation error occurs.
    """
    _dict = response_datetime(review_dict, user_timezone)
    try:
        return schema.model_validate(_dict)
    except ValidationError as e:
        mssg = f"Validation error converting review to response model: {e}"
        logger.exception("Validation error converting review to response model")
        raise ValueError(mssg) from e


# =============================================================================
# Review Endpoints
# =============================================================================


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
    deps: Annotated[ReviewOpsDeps, Depends()],
) -> ReviewResponse:
    """
    Create a new review.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    review_data : ReviewCreate
        The data for the new review.
    deps : ReviewOpsDeps
        The injected dependencies.

    Returns
    -------
    ReviewResponse
        The created review details.
    """
    db_review = await deps.repo.create(
        review_data,
        deps.current_user.uuid,
    )
    return cast(ReviewResponse, _validate_review_response(ReviewResponse, db_review))


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
    """
    Get a review by ID.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    review_id : UUID
        The unique identifier of the review.
    repo : ReviewRepoDep
        The review repository dependency.

    Returns
    -------
    ReviewResponse
        The review details if found.

    Raises
    ------
    HTTPException
        If the review is not found (404).
    """
    db_review = await repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    return cast(ReviewResponse, _validate_review_response(ReviewResponse, db_review))


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
    """
    List reviews with optional item filter.

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    repo : ReviewRepoDep
        The review repository dependency.
    deps : ReviewListQuery
        The list query parameters (itemId, skip, limit).

    Returns
    -------
    list[ReviewListResponse]
        The list of reviews.
    """
    if deps.item_id:
        reviews = await repo.get_by_item(deps.item_id, skip=deps.skip, limit=deps.limit)
    else:
        reviews = await repo.get_all(skip=deps.skip, limit=deps.limit)

    return [
        cast(ReviewListResponse, _validate_review_response(ReviewListResponse, r)) for r in reviews
    ]


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
    deps: Annotated[ReviewOpsDeps, Depends()],
) -> ReviewResponse:
    """
    Update a review (owner only).

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    review_id : UUID
        The unique identifier of the review.
    review_data : ReviewUpdate
        The update data.
    deps : ReviewOpsDeps
        The injected dependencies.

    Returns
    -------
    ReviewResponse
        The updated review details.

    Raises
    ------
    HTTPException
        If the review is not found (404).
    """
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    updated = await deps.repo.update(review_id, review_data)
    if not updated:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    return cast(ReviewResponse, _validate_review_response(ReviewResponse, updated))


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
    deps: Annotated[ReviewOpsDeps, Depends()],
) -> Response:
    """
    Delete a review (owner or admin only).

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    review_id : UUID
        The unique identifier of the review.
    deps : ReviewOpsDeps
        The injected dependencies.

    Returns
    -------
    Response
        A 204 No Content response.

    Raises
    ------
    HTTPException
        If the review is not found (404).
    """
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


# =============================================================================
# Media Helper Functions
# =============================================================================


async def _upload_images(
    review_id: UUID,
    file: UploadFile,
    db_review: ReviewDB,
) -> tuple[str, str]:
    """
    Upload an image to a review (owner only, max 5 images).

    Parameters
    ----------
    review_id : UUID
        The unique identifier of the review.
    file : UploadFile
        The image file to upload.
    db_review : ReviewDB
        The database review object.

    Returns
    -------
    tuple[str, str]
        A tuple containing (media_id, url).

    Raises
    ------
    HTTPException
        If the upload fails or limit is exceeded.
    """

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

    return media_id, url


async def _delete_image(
    review_id: UUID,
    media_id: str,
    db_review: ReviewDB,
) -> None:
    """
    Delete an image from a review (owner or admin only).

    Parameters
    ----------
    review_id : UUID
        The unique identifier of the review.
    media_id : str
        The identifier of the media to delete.
    db_review : ReviewDB
        The database review object.

    Raises
    ------
    HTTPException
        If the media is not found or deletion fails.
    """
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


async def _remove_image(review_id: UUID, media_id: str, repo: ReviewRepoDep) -> None:
    """
    Remove an image from a review record (owner or admin only).

    Parameters
    ----------
    review_id : UUID
        The unique identifier of the review.
    media_id : str
        The identifier of the media to remove.
    repo : ReviewRepoDep
        The review repository dependency.

    Raises
    ------
    HTTPException
        If the media removal fails (404).
    """
    if not await repo.remove_image_by_media_id(review_id, media_id):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")


# =============================================================================
# Media Endpoints
# =============================================================================


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
    deps: Annotated[ReviewOpsDeps, Depends()],
) -> MediaUploadResponse:
    """
    Upload an image to a review (owner only, max 5 images).

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    review_id : UUID
        The unique identifier of the review.
    file : UploadFile
        The image file to upload.
    deps : ReviewOpsDeps
        The injected dependencies.

    Returns
    -------
    MediaUploadResponse
        The upload response containing mediaId and url.

    Raises
    ------
    HTTPException
        If the review is not found (404) or upload fails.
    """
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    media_id, url = await _upload_images(review_id, file, db_review)
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
    deps: Annotated[ReviewOpsDeps, Depends()],
) -> Response:
    """
    Delete an image from a review (owner or admin only).

    Parameters
    ----------
    request : Request
        The incoming FastAPI request.
    response : Response
        The outgoing FastAPI response.
    review_id : UUID
        The unique identifier of the review.
    media_id : str
        The identifier of the media to delete.
    deps : ReviewOpsDeps
        The injected dependencies.

    Returns
    -------
    Response
        A 204 No Content response.

    Raises
    ------
    HTTPException
        If the review is not found (404) or deletion fails.
    """
    db_review = await deps.repo.get_by_id(review_id)
    if not db_review:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Review not found")

    check_owner_or_admin(db_review.user_id, deps.current_user)

    await _delete_image(review_id, media_id, db_review)
    await _remove_image(review_id, media_id, deps.repo)

    return Response(status_code=HTTP_204_NO_CONTENT)
