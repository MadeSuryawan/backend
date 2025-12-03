"""Blog API endpoints."""

from logging import getLogger
from typing import Annotated, Literal
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
from app.models import BlogDB
from app.repositories import BlogRepository
from app.schemas import BlogCreate, BlogListResponse, BlogResponse, BlogUpdate
from app.utils import response_datetime

router = APIRouter(prefix="/blogs", tags=["blogs"])

logger = file_logger(getLogger(__name__))


def db_blog_to_response(db_blog: BlogDB) -> BlogResponse:
    """
    Convert database blog model to response model.

    Args:
        db_blog: Database blog model

    Returns:
        BlogResponse: Blog response model with datetimes converted to strings
    """

    blog_dict = response_datetime(db_blog)

    try:
        response = BlogResponse.model_validate(blog_dict, from_attributes=True)
    except ValidationError as e:
        mssg = f"Validation error converting blog to response model: {e}"
        logger.exception("Validation error converting blog to response model")
        raise ValueError(mssg) from e

    return response


def db_blog_to_list_response(db_blog: BlogDB) -> BlogListResponse:
    """
    Convert database blog model to list response model.

    Args:
        db_blog: Database blog model

    Returns:
        BlogListResponse: Blog list response model with datetimes converted to strings
    """

    blog_dict = response_datetime(db_blog)

    return BlogListResponse.model_validate(blog_dict)


def get_blog_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BlogRepository:
    """
    Dependency for getting blog repository.

    Args:
        session: Database session

    Returns:
        BlogRepository: Blog repository instance
    """
    return BlogRepository(session)


@router.post(
    "/create",
    response_model=BlogResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new blog post",
    description="Create a new blog post with the provided information.",
)
async def create_blog(
    blog: BlogCreate,
    repo: Annotated[BlogRepository, Depends(get_blog_repository)],
) -> BlogResponse:
    """
    Create a new blog post.

    Args:
        blog: Blog data (must include author_id)
        repo: Blog repository

    Returns:
        BlogResponse: Created blog

    Raises:
        HTTPException: If slug already exists
    """
    try:
        # pyrefly: ignore [bad-argument-type]
        db_blog = await repo.create(blog, author_id=blog.author_id)
        return db_blog_to_response(db_blog)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.get(
    "/by-id/{blog_id}",
    response_model=BlogResponse,
    summary="Get blog by ID",
    description="Retrieve a blog post by its UUID. Increments view count.",
)
async def get_blog(
    blog_id: UUID,
    repo: Annotated[BlogRepository, Depends(get_blog_repository)],
) -> BlogResponse:
    """
    Get blog by ID and increment view count.

    Args:
        blog_id: Blog UUID
        repo: Blog repository

    Returns:
        BlogResponse: Blog data

    Raises:
        HTTPException: If blog not found
    """
    # Increment view count
    db_blog = await repo.increment_view_count(blog_id)
    if not db_blog:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Blog with ID {blog_id} not found",
        )
    return db_blog_to_response(db_blog)


@router.get(
    "/by-slug/{slug}",
    response_model=BlogResponse,
    summary="Get blog by slug",
    description="Retrieve a blog post by its slug.",
)
async def get_blog_by_slug(
    slug: str,
    repo: Annotated[BlogRepository, Depends(get_blog_repository)],
) -> BlogResponse:
    """
    Get blog by slug.

    Args:
        slug: Blog slug
        repo: Blog repository

    Returns:
        BlogResponse: Blog data

    Raises:
        HTTPException: If blog not found
    """
    db_blog = await repo.get_by_slug(slug)
    if not db_blog:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Blog with slug '{slug}' not found",
        )
    return db_blog_to_response(db_blog)


@router.get(
    "/all",
    response_model=list[BlogListResponse],
    summary="Get all blogs",
    description="Retrieve a paginated list of all blogs with optional filtering.",
)
async def get_blogs(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    status_filter: Annotated[
        Literal["draft", "published", "archived"] | None,
        Query(alias="status"),
    ] = None,
    author_id: Annotated[UUID | None, Query()] = None,
    # pyrefly: ignore [bad-function-definition]
    repo: Annotated[BlogRepository, Depends(get_blog_repository)] = None,
) -> list[BlogListResponse]:
    """
    Get all blogs with pagination and optional filtering.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        status_filter: Optional status filter (draft, published, archived)
        author_id: Optional author ID filter
        repo: Blog repository

    Returns:
        list[BlogListResponse]: List of blogs (lightweight response)
    """
    db_blogs = await repo.get_all(
        skip=skip,
        limit=limit,
        status=status_filter,
        author_id=author_id,
    )
    return [db_blog_to_list_response(blog) for blog in db_blogs]


@router.get(
    "/by-author-id/{author_id}",
    response_model=list[BlogListResponse],
    summary="Get blogs by author",
    description="Retrieve all blogs by a specific author.",
)
async def get_blogs_by_author(
    author_id: UUID,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    # pyrefly: ignore [bad-function-definition]
    repo: Annotated[BlogRepository, Depends(get_blog_repository)] = None,
) -> list[BlogListResponse]:
    """
    Get all blogs by a specific author.

    Args:
        author_id: Author UUID
        skip: Number of records to skip
        limit: Maximum number of records to return
        repo: Blog repository

    Returns:
        list[BlogListResponse]: List of blogs by the author
    """
    db_blogs = await repo.get_by_author(author_id, skip=skip, limit=limit)
    return [db_blog_to_list_response(blog) for blog in db_blogs]


@router.get(
    "/search/tags",
    response_model=list[BlogListResponse],
    summary="Search blogs by tags",
    description="Search for blogs that match any of the provided tags.",
)
async def search_blogs_by_tags(
    tags: Annotated[list[str], Query()],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    # pyrefly: ignore [bad-function-definition]
    repo: Annotated[BlogRepository, Depends(get_blog_repository)] = None,
) -> list[BlogListResponse]:
    """
    Search blogs by tags.

    Args:
        tags: List of tags to search for
        skip: Number of records to skip
        limit: Maximum number of records to return
        repo: Blog repository

    Returns:
        list[BlogListResponse]: List of blogs matching any of the tags
    """
    db_blogs = await repo.search_by_tags(tags, skip=skip, limit=limit)
    return [db_blog_to_list_response(blog) for blog in db_blogs]


@router.put(
    "/update/{blog_id}",
    response_model=BlogResponse,
    summary="Update blog",
    description="Update blog information. Only provided fields will be updated.",
)
async def update_blog(
    blog_id: UUID,
    blog_update: BlogUpdate,
    repo: Annotated[BlogRepository, Depends(get_blog_repository)],
) -> BlogResponse:
    """
    Update blog information.

    Args:
        blog_id: Blog UUID
        blog_update: Blog update data
        repo: Blog repository

    Returns:
        BlogResponse: Updated blog

    Raises:
        HTTPException: If blog not found or slug already exists
    """
    try:
        db_blog = await repo.update(blog_id, blog_update)
        if not db_blog:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Blog with ID {blog_id} not found",
            )
        return db_blog_to_response(db_blog)
    except ValueError as e:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.delete(
    "/delete/{blog_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete blog",
    description="Delete a blog post by its UUID.",
)
async def delete_blog(
    blog_id: UUID,
    repo: Annotated[BlogRepository, Depends(get_blog_repository)],
) -> None:
    """
    Delete blog by ID.

    Args:
        blog_id: Blog UUID
        repo: Blog repository

    Raises:
        HTTPException: If blog not found
    """
    deleted = await repo.delete(blog_id)
    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Blog with ID {blog_id} not found",
        )
