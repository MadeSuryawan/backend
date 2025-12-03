# app/routes/user.py
"""User API endpoints."""

from logging import getLogger
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
)

from app.configs import file_logger
from app.db import get_session
from app.models import UserDB
from app.repositories import UserRepository
from app.schemas import UserCreate, UserResponse, UserUpdate
from app.utils import response_datetime

router = APIRouter(prefix="/users", tags=["users"])

logger = file_logger(getLogger(__name__))


def db_user_to_response(db_user: UserDB) -> UserResponse:
    """
    Convert database user model to response model.

    Args:
        db_user: Database user model (UserDB)

    Returns:
        UserResponse: User response model
    """

    user_dict = response_datetime(db_user)
    try:
        response = UserResponse.model_validate(user_dict, from_attributes=True)
    except ValidationError as e:
        mssg = f"Validation error converting user to response model: {e}"
        logger.exception("Validation error converting user to response model")
        raise ValueError(mssg) from e

    return response


def get_user_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRepository:
    """
    Dependency for getting user repository.

    Args:
        session: Database session

    Returns:
        UserRepository: User repository instance
    """
    return UserRepository(session)


RepoDep = Annotated[UserRepository, Depends(get_user_repository)]


@router.post(
    "/create",
    response_model=UserResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new user",
    description="Create a new user account with the provided information.",
)
async def create_user(
    user: UserCreate,
    repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """
    Create a new user.

    Args:
        user: User data
        repo: User repository

    Returns:
        UserResponse: Created user (without password)

    Raises:
        HTTPException: If username or email already exists
    """
    try:
        db_user = await repo.create(user)
        return db_user_to_response(db_user)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/all",
    response_model=list[UserResponse] | str,
    summary="Get all users",
    description="Retrieve a paginated list of all users.",
)
async def get_users(
    repo: RepoDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[UserResponse] | str:
    """
    Get all users with pagination.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        repo: User repository

    Returns:
        list[UserResponse]: List of users (without passwords)
    """
    db_users = await repo.get_all(skip=skip, limit=limit)
    if not db_users:
        return "No users found"
    return [db_user_to_response(user) for user in db_users]


@router.get(
    "/by-id/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
    description="Retrieve a user by their UUID.",
)
async def get_user(
    user_id: UUID,
    repo: RepoDep,
) -> UserResponse:
    """
    Get user by ID.

    Args:
        user_id: User UUID
        repo: User repository

    Returns:
        UserResponse: User data (without password)

    Raises:
        HTTPException: If user not found
    """
    db_user = await repo.get_by_id(user_id)
    if not db_user:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
    return db_user_to_response(db_user)


@router.get(
    "/by-username/{username}",
    response_model=UserResponse,
    summary="Get user by username",
    description="Retrieve a user by their username.",
)
async def get_user_by_username(
    username: str,
    repo: RepoDep,
) -> UserResponse:
    """
    Get user by username.

    Args:
        username: Username
        repo: User repository

    Returns:
        UserResponse: User data (without password)

    Raises:
        HTTPException: If user not found
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
    response_model=UserResponse,
    summary="Update user",
    description="Update user information. Only provided fields will be updated.",
)
async def update_user(
    user_id: UUID,
    user_update: UserUpdate,
    repo: RepoDep,
) -> UserResponse:
    """
    Update user information.

    Args:
        user_id: User UUID
        user_update: User update data
        repo: User repository

    Returns:
        UserResponse: Updated user (without password)

    Raises:
        HTTPException: If user not found or email already exists
    """
    try:
        db_user = await repo.update(user_id, user_update)
        if not db_user:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found",
            )
        return db_user_to_response(db_user)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete(
    "/delete/{user_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Delete a user by their UUID.",
)
async def delete_user(
    user_id: UUID,
    repo: RepoDep,
) -> None:
    """
    Delete user by ID.

    Args:
        user_id: User UUID
        repo: User repository

    Raises:
        HTTPException: If user not found
    """
    deleted = await repo.delete(user_id)
    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found",
        )
