# app/routes/user.py

"""
User Routes.

Provides CRUD endpoints for user accounts with consistent documentation and
rate limiting aligned to established route patterns.

Summary
-------
Endpoints include:
  - Create user
  - Get all users
  - Get user by id
  - Get user by username
  - Update user
  - Delete user

Dependencies
------------
  - `UserOpsDeps`: Bundles repository and current user for authenticated operations.

Rate Limiting
-------------
All endpoints define explicit limits and include `429` response examples. Tiered
limits apply when `X-API-Key` is present, offering higher throughput for
authenticated/identified clients.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError
from starlette.responses import Response
from starlette.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from app.auth.permissions import check_owner_or_admin
from app.decorators.caching import cache_busting, cached, get_cache_manager
from app.decorators.metrics import timed
from app.dependencies import AdminUserDep, AuthServiceDep, UserDBDep, UserQueryListDep, UserRepoDep
from app.errors.database import DatabaseError, DuplicateEntryError
from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageTypeError,
)
from app.managers.rate_limiter import limiter
from app.models import UserDB
from app.schemas import TestimonialUpdate, UserCreate, UserResponse, UserUpdate
from app.services.profile_picture import ProfilePictureService
from app.utils.cache_keys import user_id_key, username_key, users_list_key
from app.utils.helpers import file_logger, host, response_datetime

router = APIRouter(prefix="/users", tags=["👤 Users"])

logger = file_logger(getLogger(__name__))


def db_user_to_response(db_user: UserDB) -> UserResponse:
    """
    Convert a `UserDB` instance to `UserResponse` with datetime serialization.

    Parameters
    ----------
    db_user : UserDB
        Database user entity.

    Returns
    -------
    UserResponse
        Validated response model.
    """

    user_dict = response_datetime(db_user)

    # Handle updated_at which might be "No updates" string from helpers.response_datetime
    # But UserResponse expects datetime | None.
    # If "No updates", we set it to None.
    if user_dict.get("updated_at") == "No updates":
        user_dict["updated_at"] = None

    try:
        response = UserResponse.model_validate(user_dict, from_attributes=True)
    except ValidationError as e:
        mssg = f"Validation error converting user to response model: {e}"
        logger.exception("Validation error converting user to response model")
        raise ValueError(mssg) from e

    return response


@dataclass(frozen=True)
class UserOpsDeps:
    """Dependencies for authenticated user operations."""

    user_id: UUID
    repo: UserRepoDep
    current_user: UserDBDep


def handle_db_error(e: DatabaseError) -> HTTPException:
    """
    Convert database errors to HTTP exceptions.

    Parameters
    ----------
    e : DatabaseError
        Database error instance.

    Returns
    -------
    HTTPException
        Standardized error response.
    """
    if isinstance(e, DuplicateEntryError):
        return HTTPException(status_code=HTTP_409_CONFLICT, detail=e.detail)
    return HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=e.detail)


def handle_image_error(e: Exception) -> HTTPException:
    """
    Convert image processing errors to HTTP exceptions.

    Parameters
    ----------
    e : Exception
        The image processing error.

    Returns
    -------
    HTTPException
        Standardized error response.
    """
    match e:
        case UnsupportedImageTypeError():
            return HTTPException(status_code=HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=e.detail)
        case ImageTooLargeError():
            return HTTPException(status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=e.detail)
        case InvalidImageError() | ImageProcessingError():
            return HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=e.detail)
        case _:
            return HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e))


@asynccontextmanager
async def db_operation_context() -> AsyncGenerator[None]:
    """
    Context manager for database operations with standardized error handling.

    Yields
    ------
    None
        Execution control back to caller.

    Raises
    ------
    HTTPException
        Converted database error.
    """
    try:
        yield
    except DuplicateEntryError as e:
        raise handle_db_error(e) from e
    except DatabaseError as e:
        raise handle_db_error(e) from e


# =============================================================================
# Helper Functions
# =============================================================================


async def _handle_email_change(
    db_user: UserDB,
    existing_user: UserDB,
    auth_service: AuthServiceDep,
    repo: UserRepoDep,
) -> None:
    """
    Handle email change: mark user unverified and send verification email.

    Parameters
    ----------
    db_user : UserDB
        The updated user record.
    existing_user : UserDB
        The user record before update.
    auth_service : AuthServiceDep
        Authentication service.
    repo : UserRepoDep
        User repository.
    """
    logger.info(
        "Email changed for user %s: %s -> %s. Re-verification required.",
        db_user.uuid,
        existing_user.email,
        db_user.email,
    )
    db_user.is_verified = False
    await repo._add_and_refresh(db_user)
    await auth_service.send_verification_email(db_user)
    await auth_service.record_verification_sent(db_user.uuid)
    logger.info("Verification email sent to new address: %s", db_user.email)


async def _get_user_or_404(repo: UserRepoDep, user_id: UUID) -> UserDB:
    """
    Retrieve user by ID or raise 404 if not found.

    Parameters
    ----------
    repo : UserRepoDep
        User repository instance.
    user_id : UUID
        User identifier.

    Returns
    -------
    UserDB
        The user database entity.

    Raises
    ------
    HTTPException
        404 if user not found.
    """
    db_user = await repo.get_by_id(user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    return db_user


async def _get_authorized_user(
    repo: UserRepoDep,
    user_id: UUID,
    current_user: UserDB,
    resource_name: str = "user",
) -> UserDB:
    """
    Retrieve user and verify authorization (owner or admin).

    Parameters
    ----------
    repo : UserRepoDep
        User repository instance.
    user_id : UUID
        Target user identifier.
    current_user : UserDB
        Currently authenticated user.
    resource_name : str
        Resource name for error messages.

    Returns
    -------
    UserDB
        The authorized user database entity.

    Raises
    ------
    HTTPException
        404 if user not found, 403 if not authorized.
    """
    db_user = await _get_user_or_404(repo, user_id)
    check_owner_or_admin(user_id, current_user, resource_name)
    return db_user


async def _invalidate_user_cache(
    request: Request,
    user_id: UUID,
    username: str,
) -> None:
    """
    Invalidate cache entries for a user.

    Parameters
    ----------
    request : Request
        Current request context.
    user_id : UUID
        User identifier.
    username : str
        User's username.
    """
    await get_cache_manager(request).delete(
        user_id_key(user_id),
        username_key(username),
        users_list_key(0, 10),
        namespace="users",
    )


def _success_response(message: str = "success") -> ORJSONResponse:
    """Create a standardized success response for cache operations."""
    return ORJSONResponse(content={"status": message})


def _get_pp_service() -> ProfilePictureService:
    """
    Get ProfilePictureService instance.

    Returns
    -------
    ProfilePictureService
        Service instance for profile picture operations.
    """
    return ProfilePictureService()


async def _upload_pp(
    user_id: str,
    file: UploadFile,
) -> str:
    """
    Upload profile picture with standardized error handling.

    Parameters
    ----------
    user_id : str
        User identifier.
    file : UploadFile
        Image file to upload.

    Returns
    -------
    str
        URL of the uploaded picture.

    Raises
    ------
    HTTPException
        On image processing errors.
    """
    try:
        return await _get_pp_service().upload_profile_picture(
            user_id=user_id,
            file=file,
        )
    except (
        UnsupportedImageTypeError,
        ImageTooLargeError,
        InvalidImageError,
        ImageProcessingError,
    ) as e:
        raise handle_image_error(e) from e


# =============================================================================
# User Endpoints
# =============================================================================


@router.post(
    "/create",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user account with the provided information.",
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "firstName": "John",
                        "lastName": "Doe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                        "createdAt": "2025-01-01",
                        "updatedAt": "2025-01-01",
                        "country": "N/A",
                        "displayName": "John Doe",
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {
                "application/json": {"example": {"detail": "Username or email already exists"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_create",
)
@timed("/users/create")
@limiter.limit(lambda key: "15/hour" if "apikey" in key else "5/hour")
@cache_busting(
    key_builder=lambda **kw: [users_list_key(0, 10)],
    namespace="users",
)
async def create_user(
    request: Request,
    response: Response,
    user: Annotated[
        UserCreate,
        Body(
            examples={
                "basic": {
                    "summary": "Basic user creation",
                    "value": {
                        "userName": "johndoe",
                        "firstName": "John",
                        "lastName": "Doe",
                        "email": "johndoe@gmail.com",
                        "password": "password123",
                        "bio": "Traveler and blogger",
                    },
                },
            },
        ),
    ],
    repo: UserRepoDep,
    admin_user: AdminUserDep,
) -> UserResponse:
    """
    Create a new user and return the safe response model.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user : UserCreate
        User input payload.
    repo : UserRepository
        Repository dependency.
    admin_user : AdminUserDep
        Admin user dependency.

    Returns
    -------
    UserResponse
        Created user (without password).

    Raises
    ------
    HTTPException
        If username or email already exists.
    """
    async with db_operation_context():
        db_user = await repo.create(user)
        await _invalidate_user_cache(request, db_user.uuid, db_user.username)
        return db_user_to_response(db_user)


@router.get(
    "/all",
    response_class=ORJSONResponse,
    response_model=list[UserResponse] | str,
    summary="Get all users",
    description="Retrieve a paginated list of all users.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "username": "johndoe",
                            "firstName": "John",
                            "lastName": "Doe",
                            "email": "johndoe@gmail.com",
                            "isActive": True,
                            "isVerified": False,
                            "createdAt": "2025-01-01",
                            "updatedAt": "2025-01-01",
                        },
                    ],
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_get_all",
)
@timed("/users/all")
@limiter.limit(lambda key: "30/minute" if "apikey" in key else "10/minute")
@cached(
    ttl=3600,
    namespace="users",
    key_builder=lambda **kw: users_list_key(kw.get("skip", 0), kw.get("limit", 10)),
)
async def get_users(
    request: Request,
    response: Response,
    repo: UserRepoDep,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
) -> list[UserResponse] | str:
    """
    Get all users with pagination.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    list[UserResponse] | str
        List of users or informational message when none found.
    """
    db_users = await repo.get_all(skip=skip, limit=limit)
    if not db_users:
        return "No users found"
    return [db_user_to_response(user) for user in db_users]


@router.get(
    "/by-id/{user_id}",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Get user by ID",
    description="Retrieve a user by their UUID.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_get_by_id",
)
@timed("/users/by-id")
@limiter.limit(lambda key: "60/minute" if "apikey" in key else "20/minute")
@cached(
    ttl=1800,
    namespace="users",
    key_builder=lambda **kw: user_id_key(kw["user_id"]),
    response_model=UserResponse,
)
async def get_user(
    request: Request,
    response: Response,
    user_id: UUID,
    repo: UserRepoDep,
) -> UserResponse:
    """
    Get user by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    UserResponse
        User data without sensitive fields.

    Raises
    ------
    HTTPException
        If user not found.
    """
    db_user = await _get_user_or_404(repo, user_id)
    return db_user_to_response(db_user)


@router.get(
    "/by-username/{username}",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Get user by username",
    description="Retrieve a user by their username.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {
                    "example": {"detail": "User with username 'johndoe' not found"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_get_by_username",
)
@timed("/users/by-username")
@limiter.limit(lambda key: "60/minute" if "apikey" in key else "20/minute")
@cached(
    ttl=1800,
    namespace="users",
    key_builder=lambda **kw: username_key(kw["username"]),
    response_model=UserResponse,
)
async def get_user_by_username(
    request: Request,
    response: Response,
    username: str,
    repo: UserRepoDep,
) -> UserResponse:
    """
    Get user by username.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    username : str
        Username value.
    repo : UserRepository
        Repository dependency.

    Returns
    -------
    UserResponse
        User data without sensitive fields.

    Raises
    ------
    HTTPException
        If user not found.
    """
    db_user = await repo.get_by_username(username)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with username '{username}' not found",
        )
    return db_user_to_response(db_user)


@router.put(
    "/update/{user_id}",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    summary="Update user",
    description="Update user information. Only provided fields will be updated.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "email": "johndoe@gmail.com",
                        "isActive": True,
                        "isVerified": False,
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {"application/json": {"example": {"detail": "Email already exists"}}},
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_update",
)
@timed("/users/update")
@limiter.limit(lambda key: "20/minute" if "apikey" in key else "5/minute")
@cache_busting(
    key_builder=lambda deps, **kw: [user_id_key(deps.user_id), users_list_key(0, 10)],
    namespace="users",
)
async def update_user(
    request: Request,
    response: Response,
    user_update: Annotated[
        UserUpdate,
        Body(
            examples={
                "basic": {
                    "summary": "Update display fields",
                    "value": {
                        "firstName": "Johnny",
                        "lastName": "D",
                        "bio": "Globetrotter",
                    },
                },
                "email_change": {
                    "summary": "Update email (triggers re-verification)",
                    "value": {
                        "email": "newemail@example.com",
                    },
                },
            },
        ),
    ],
    deps: Annotated[UserOpsDeps, Depends()],
    auth_service: AuthServiceDep,
) -> UserResponse:
    """
    Update user information and return the safe response model.

    If the email is changed, the user will be marked as unverified and
    a new verification email will be sent to the new address.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_update : UserUpdate
        Update payload (partial updates accepted).
    deps : UserOpsDeps
        Operation dependencies (repo + current_user).
    auth_service : AuthServiceDep
        Authentication service for sending verification emails.

    Returns
    -------
    UserResponse
        Updated user without sensitive fields.

    Raises
    ------
    HTTPException
        If user not found or invalid update.
    """
    check_owner_or_admin(deps.user_id, deps.current_user, "user")

    async with db_operation_context():
        existing = await _get_user_or_404(deps.repo, deps.user_id)
        email_changed = bool(
            user_update.email and user_update.email != existing.email,
        )

        db_user = await deps.repo.update(deps.user_id, user_update)
        if not db_user:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"User with ID {deps.user_id} not found",
            )

        if email_changed:
            await _handle_email_change(db_user, existing, auth_service, deps.repo)

        if existing.username != db_user.username:
            await get_cache_manager(request).delete(
                username_key(existing.username),
                namespace="users",
            )

        await _invalidate_user_cache(request, deps.user_id, db_user.username)
        return db_user_to_response(db_user)


@router.delete(
    "/delete/{user_id}",
    response_class=ORJSONResponse,
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user by their UUID.",
    responses={
        204: {"description": "No Content"},
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_delete",
)
@timed("/users/delete")
@limiter.limit(lambda key: "10/minute" if "apikey" in key else "2/minute")
@cache_busting(
    key_builder=lambda deps, **kw: [user_id_key(deps.user_id), users_list_key(0, 10)],
    namespace="users",
)
async def delete_user(
    request: Request,
    response: Response,
    deps: Annotated[UserOpsDeps, Depends()],
) -> Response:
    """
    Delete user by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    deps : UserOpsDeps
        Operation dependencies (repo + current_user).

    Raises
    ------
    HTTPException
        If user not found.
    """
    # Get user and verify authorization
    existing = await _get_user_or_404(deps.repo, deps.user_id)
    check_owner_or_admin(deps.user_id, deps.current_user, "user")

    # Delete profile picture if it exists
    if existing.profile_picture:
        try:
            await _get_pp_service().delete_profile_picture(str(deps.user_id))
        except Exception:
            logger.exception(
                "Failed to delete profile picture for user %s during deletion",
                deps.user_id,
            )

    # Delete the user
    if not await deps.repo.delete(deps.user_id):
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user, Please try again later.",
        )

    # Invalidate cache for deleted user
    await _invalidate_user_cache(request, deps.user_id, existing.username)
    return Response(status_code=HTTP_204_NO_CONTENT)


# =============================================================================
# User Profile Picture Endpoints
# =============================================================================


@router.post(
    "/{user_id}/profile-picture",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    status_code=HTTP_200_OK,
    summary="Upload profile picture",
    description="Upload or replace a user's profile picture. Accepts JPEG, PNG, or WebP images up to 5MB.",
    responses={
        200: {
            "description": "Profile picture uploaded successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "username": "johndoe",
                        "profilePicture": "https://res.cloudinary.com/.../profile.jpg",
                    },
                },
            },
        },
        400: {
            "description": "Invalid image file",
            "content": {
                "application/json": {"example": {"detail": "Invalid or corrupted image file"}},
            },
        },
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {"example": {"detail": "Not authorized to modify this user"}},
            },
        },
        404: {
            "description": "User not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        413: {
            "description": "Image too large",
            "content": {
                "application/json": {
                    "example": {"detail": "Image size exceeds maximum allowed size of 5MB"},
                },
            },
        },
        415: {
            "description": "Unsupported image type",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Unsupported image type. Allowed: image/jpeg, image/png, image/webp",
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_upload_profile_picture",
)
@timed("/users/{user_id}/profile-picture")
@limiter.limit("10/hour")
@cache_busting(
    key_builder=lambda deps, **kw: [user_id_key(deps.user_id), users_list_key(0, 10)],
    namespace="users",
)
async def upload_profile_picture(
    request: Request,
    response: Response,
    file: UploadFile,
    deps: Annotated[UserOpsDeps, Depends()],
) -> UserResponse:
    """
    Upload or replace a user's profile picture.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    file : UploadFile
        Uploaded image file.
    deps : UserOpsDeps
        Operation dependencies (repo + current_user).

    Returns
    -------
    UserResponse
        Updated user with new profile picture URL.

    Raises
    ------
    HTTPException
        If user not found, unauthorized, or invalid image.
    """
    db_user = await _get_authorized_user(deps.repo, deps.user_id, deps.current_user)
    picture_url = await _upload_pp(str(deps.user_id), file)

    updated_user = await deps.repo.update(deps.user_id, {"profile_picture": picture_url})
    if not updated_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {deps.user_id} not found",
        )

    await _invalidate_user_cache(request, deps.user_id, db_user.username)
    return db_user_to_response(updated_user)


@router.delete(
    "/{user_id}/profile-picture",
    response_class=ORJSONResponse,
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete profile picture",
    description="Delete a user's profile picture. The user will revert to a default avatar.",
    responses={
        204: {"description": "Profile picture deleted successfully"},
        400: {
            "description": "No profile picture to delete",
            "content": {
                "application/json": {"example": {"detail": "No profile picture to delete"}},
            },
        },
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {"example": {"detail": "Not authorized to modify this user"}},
            },
        },
        404: {
            "description": "User not found",
            "content": {
                "application/json": {"example": {"detail": "User with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="users_delete_profile_picture",
)
@timed("/users/{user_id}/profile-picture")
@limiter.limit("10/hour")
@cache_busting(
    key_builder=lambda deps, **kw: [user_id_key(deps.user_id), users_list_key(0, 10)],
    namespace="users",
)
async def delete_profile_picture(
    request: Request,
    response: Response,
    deps: Annotated[UserOpsDeps, Depends()],
) -> Response:
    """
    Delete a user's profile picture.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    deps : UserOpsDeps
        Operation dependencies (repo + current_user).

    Raises
    ------
    HTTPException
        If user not found, unauthorized, or no picture to delete.
    """
    # Get user and verify authorization
    db_user = await _get_authorized_user(deps.repo, deps.user_id, deps.current_user)

    # Check if user has a profile picture
    if not db_user.profile_picture:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="No profile picture to delete",
        )

    # Delete from storage
    if not await _get_pp_service().delete_profile_picture(str(deps.user_id)):
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete profile picture, Please try again later.",
        )

    # Update user's profile_picture field to None
    await deps.repo.update(deps.user_id, {"profile_picture": None})

    # Invalidate cache
    await _invalidate_user_cache(request, deps.user_id, db_user.username)
    return Response(status_code=HTTP_204_NO_CONTENT)


# =============================================================================
# User Testimonial Endpoints
# =============================================================================


@router.patch(
    "/{user_id}/testimonial",
    response_class=ORJSONResponse,
    response_model=UserResponse,
    status_code=HTTP_200_OK,
    summary="Update user testimonial",
    description="Update testimonial for an authenticated user.",
    responses={
        200: {"description": "Testimonial updated successfully"},
        403: {"description": "Not authorized to update this user's testimonial"},
        404: {"description": "User not found"},
        429: {"description": "Rate limit exceeded"},
    },
    operation_id="users_update_testimonial",
)
@timed("/users/{user_id}/testimonial")
@limiter.limit(lambda key: "10/hour" if "apikey" in key else "5/hour")
@cache_busting(
    key_builder=lambda deps, **kw: [user_id_key(deps.user_id)],
    namespace="users",
)
async def update_testimonial(
    request: Request,
    response: Response,
    payload: Annotated[TestimonialUpdate, Body(...)],
    deps: Annotated[UserOpsDeps, Depends()],
) -> UserResponse:
    """
    Update user testimonial.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    payload : TestimonialUpdate
        Testimonial content.
    deps : UserOpsDeps
        Authenticated user operation dependencies.

    Returns
    -------
    UserResponse
        Updated user record.

    Raises
    ------
    HTTPException
        If user not found or unauthorized.
    """
    db_user = await _get_authorized_user(deps.repo, deps.user_id, deps.current_user, "testimonial")
    updated_user = await deps.repo.update(deps.user_id, {"testimonial": payload.testimonial})
    if not updated_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {deps.user_id} not found",
        )
    await _invalidate_user_cache(request, deps.user_id, db_user.username)
    return db_user_to_response(updated_user)


@router.delete(
    "/{user_id}/testimonial",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete user testimonial",
    description="Remove a testimonial. Accessible by the owner or an administrator.",
    responses={
        204: {"description": "Testimonial deleted successfully"},
        403: {"description": "Not authorized to delete this user's testimonial"},
        404: {"description": "User not found"},
        429: {"description": "Rate limit exceeded"},
    },
    operation_id="users_delete_testimonial",
)
@timed("/users/{user_id}/testimonial")
@limiter.limit("5/hour")
@cache_busting(
    key_builder=lambda deps, **kw: [user_id_key(deps.user_id)],
    namespace="users",
)
async def delete_testimonial(
    request: Request,
    response: Response,
    deps: Annotated[UserOpsDeps, Depends()],
) -> Response:
    """
    Delete user testimonial.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    deps : UserOpsDeps
        Authenticated user operation dependencies.

    Returns
    -------
    Response
        HTTP 204 No Content on success.

    Raises
    ------
    HTTPException
        If user not found or unauthorized.
    """
    db_user = await _get_authorized_user(deps.repo, deps.user_id, deps.current_user, "testimonial")
    if not await deps.repo.update(deps.user_id, {"testimonial": None}):
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {deps.user_id} not found",
        )
    await _invalidate_user_cache(request, deps.user_id, db_user.username)
    return Response(status_code=HTTP_204_NO_CONTENT)


# =============================================================================
# Cache Busting Endpoints
# =============================================================================


@router.post(
    "/bust-list",
    response_class=ORJSONResponse,
    summary="Bust users list cache page",
    description="Invalidate cached users list page for given `skip` and `limit`.",
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_list",
)
@timed("/users/bust-list")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda **kw: [users_list_key(kw.get("skip", 0), kw.get("limit", 10))],
    namespace="users",
)
async def bust_users_list(
    request: Request,
    response: Response,
    *,
    skip: Annotated[int, Query(ge=0, description="Number of records to skip.")],
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return.")],
) -> ORJSONResponse:
    """
    Bust users list cache page.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.

    Returns
    -------
    ORJSONResponse
        Success status.
    """
    return _success_response()


@router.post(
    "/bust-by-id",
    response_class=ORJSONResponse,
    summary="Bust cached user by ID",
    description="Invalidate cached user detail for a given UUID.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_by_id",
)
@timed("/users/bust-by-id")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda user_id, **kw: [user_id_key(user_id)],
    namespace="users",
)
async def bust_user_by_id(
    request: Request,
    response: Response,
    user_id: UUID,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Bust cached user by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    user_id : UUID
        User identifier to invalidate.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Success status.
    """
    return _success_response()


@router.post(
    "/bust-by-username",
    response_class=ORJSONResponse,
    summary="Bust cached user by username",
    description="Invalidate cached user detail for a given username.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_by_username",
)
@timed("/users/bust-by-username")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda username, **kw: [username_key(username)],
    namespace="users",
)
async def bust_user_by_username(
    request: Request,
    response: Response,
    username: str,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Bust cached user by username.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    username : str
        Username to invalidate.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Success status.
    """
    return _success_response()


@router.post(
    "/bust-list-multi",
    response_class=ORJSONResponse,
    summary="Bust multiple users list cache pages",
    description="Invalidate cached users list pages across multiple `limit` values.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_list_multi",
)
@timed("/users/bust-list-multi")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda query, limits, **kw: [
        users_list_key(query.skip, limit_value) for limit_value in limits
    ],
    namespace="users",
)
async def bust_users_list_multi(
    request: Request,
    response: Response,
    query: UserQueryListDep,
    limits: Annotated[list[int], Query(description="List of limit values to invalidate.")],
) -> ORJSONResponse:
    """
    Bust multiple users list cache pages.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    query : UserQueryListDep
        Query parameters for skip/limit.
    limits : list[int]
        List of limit values to invalidate.

    Returns
    -------
    ORJSONResponse
        Success status.

    Raises
    ------
    HTTPException
        If not accessed via localhost.
    """
    if host(request) not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Admin access required (localhost only)",
        )
    return _success_response()


@router.post(
    "/bust-list-grid",
    response_class=ORJSONResponse,
    summary="Bust users list pages across limits and skips",
    description="Invalidate cached users list pages across multiple `limit` and `skip` values.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "success"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_list_grid",
)
@timed("/users/bust-list-grid")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda skip, limit, **kw: [users_list_key(s, lim) for lim in limit for s in skip],
    namespace="users",
)
async def bust_users_list_grid(
    request: Request,
    response: Response,
    skip: Annotated[list[int], Query(description="List of skip values to invalidate.")],
    limit: Annotated[list[int], Query(description="List of limit values to invalidate.")],
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Bust users list cache pages across multiple skip/limit combinations.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    skip : list[int]
        List of skip values to invalidate.
    limit : list[int]
        List of limit values to invalidate.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Success status.
    """
    return _success_response()


@router.delete(
    "/bust-all",
    response_class=ORJSONResponse,
    summary="Clear users cache namespace",
    description="Clear all cached keys in the users namespace.",
    responses={
        200: {"content": {"application/json": {"example": {"status": "cleared"}}}},
        403: {
            "description": "Forbidden",
            "content": {
                "application/json": {
                    "example": {"detail": "Admin access required"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="users_bust_all",
)
@timed("/users/bust-all")
@limiter.limit("5/minute")
async def bust_users_all(
    request: Request,
    response: Response,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Clear all cached keys in the users namespace.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Success status with "cleared" message.
    """
    await get_cache_manager(request).clear(namespace="users")
    return _success_response("cleared")
