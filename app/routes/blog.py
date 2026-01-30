# app/routes/blog.py

"""
Blog Routes.

Provides CRUD endpoints and listing/search for blogs with standardized
documentation and rate limiting aligned to established route patterns.

Summary
-------
Endpoints include:
  - Create blog
  - Get blog by id
  - Get blog by slug
  - List blogs (with filters)
  - List blogs by author
  - Search blogs by tags
  - Update blog
  - Delete blog

Dependencies
------------
  - `BlogOpsDeps`: Bundles repository and current user for authenticated operations.

Rate Limiting
-------------
All endpoints define explicit limits and include `429` response examples. Tiered
limits apply when `X-API-Key` is present, offering higher throughput for
authenticated/identified clients.
"""

from dataclasses import dataclass
from logging import getLogger
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import ORJSONResponse
from pydantic import ValidationError
from starlette.responses import Response
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from app.auth.permissions import AdminUserDep, check_owner_or_admin
from app.decorators.caching import cache_busting, cached, get_cache_manager
from app.decorators.metrics import timed
from app.dependencies import BlogListQuery, BlogQueryListDep, BlogRepoDep, UserDBDep
from app.errors.database import DatabaseError, DuplicateEntryError
from app.errors.upload import (
    ImageProcessingError,
    ImageTooLargeError,
    InvalidImageError,
    MediaLimitExceededError,
    UnsupportedImageTypeError,
    UnsupportedVideoTypeError,
    VideoTooLargeError,
)
from app.managers.rate_limiter import limiter
from app.models import BlogDB
from app.schemas import BlogCreate, BlogListResponse, BlogResponse, BlogSchema, BlogUpdate
from app.schemas.review import MediaUploadResponse
from app.services import MediaService
from app.utils.helpers import file_logger, response_datetime

router = APIRouter(prefix="/blogs", tags=["📝 Blogs"])

logger = file_logger(getLogger(__name__))


@dataclass(frozen=True)
class BlogOpsDeps:
    """Dependencies for authenticated blog operations."""

    repo: BlogRepoDep
    current_user: UserDBDep


@dataclass(frozen=True)
class PaginationQuery:
    """
    Query container for pagination.

    Parameters
    ----------
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    """

    skip: int = 0
    limit: int = 10


@dataclass(frozen=True)
class BustListGridQuery:
    """
    Query container for grid cache busting.

    Parameters
    ----------
    limits : list[int]
        List of limit values to invalidate.
    skips : list[int]
        List of skip values to invalidate.
    """

    limits: list[int]
    skips: list[int]


def db_blog_to_response(db_blog: BlogDB) -> BlogResponse:
    """
    Convert a `BlogDB` instance to `BlogResponse` with datetime serialization.

    Parameters
    ----------
    db_blog : BlogDB
        Database blog entity.

    Returns
    -------
    BlogResponse
        Validated response model.
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
    Convert a `BlogDB` instance to `BlogListResponse` with datetime serialization.

    Parameters
    ----------
    db_blog : BlogDB
        Database blog entity.

    Returns
    -------
    BlogListResponse
        Validated list response model.
    """

    blog_dict = response_datetime(db_blog)

    return BlogListResponse.model_validate(blog_dict)


def get_pagination_query(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
) -> PaginationQuery:
    """
    Dependency to construct `PaginationQuery` from query parameters.

    Returns
    -------
    PaginationQuery
        Aggregated pagination parameters.
    """
    return PaginationQuery(skip=skip, limit=limit)


def get_bust_list_grid_query(
    limits: Annotated[list[int], Query(description="List of limit values to invalidate.")],
    skips: Annotated[list[int], Query(description="List of skip values to invalidate.")],
) -> BustListGridQuery:
    """
    Dependency to construct `BustListGridQuery` from query parameters.

    Returns
    -------
    BustListGridQuery
        Aggregated grid parameters.
    """
    return BustListGridQuery(limits=limits, skips=skips)


def blog_slug_key(slug: str) -> str:
    """
    Generate cache key for blog by slug.

    Parameters
    ----------
    slug : str
        Blog slug.

    Returns
    -------
    str
        Cache key for blog by slug.
    """
    return f"blog_by_slug_{slug}"


def blogs_list_key(query: BlogListQuery) -> str:
    """
    Generate cache key for blogs list.

    Parameters
    ----------
    query : BlogListQuery
        Blog list query parameters.

    Returns
    -------
    str
        Cache key for blogs list.
    """
    status_part = query.status_filter or "any"
    author_part = str(query.author_id) if query.author_id else "any"
    return f"blogs_all_{query.skip}_{query.limit}_{status_part}_{author_part}"


def blogs_by_author_key(author_id: UUID, pagination: PaginationQuery) -> str:
    """
    Generate cache key for blogs by author.

    Parameters
    ----------
    author_id : UUID
        Author ID.
    pagination : PaginationQuery
        Pagination parameters.

    Returns
    -------
    str
        Cache key for blogs by author.
    """
    return f"blogs_by_author_{author_id}_{pagination.skip}_{pagination.limit}"


def blogs_search_tags_key(tags: list[str], pagination: PaginationQuery) -> str:
    """
    Generate cache key for blogs search by tags.

    Parameters
    ----------
    tags : list[str]
        List of tags to search for.
    pagination : PaginationQuery
        Pagination parameters.

    Returns
    -------
    str
        Cache key for blogs search by tags.
    """
    tags_part = "-".join(sorted(tags)) or "none"
    return f"blogs_search_{tags_part}_{pagination.skip}_{pagination.limit}"


@router.post(
    "/create",
    response_class=ORJSONResponse,
    response_model=BlogResponse,
    status_code=HTTP_201_CREATED,
    summary="Create a new blog post",
    description="Create a new blog post with the provided information.",
    responses={
        201: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "authorId": "123e4567-e89b-12d3-a456-426614174111",
                        "title": "What to Pack for Your Bali Trip: The Essentials",
                        "slug": "what-to-pack-for-your-bali-trip-the-essentials",
                        "summary": "A practical packing guide for Bali",
                        "content": "...",
                        "viewCount": 0,
                        "tags": ["bali", "travel"],
                        "status": "draft",
                        "createdAt": "2025-01-01",
                        "updatedAt": "2025-01-01",
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {"application/json": {"example": {"detail": "Slug already exists"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="blogs_create",
)
@timed("/blogs/create")
@limiter.limit(lambda key: "10/minute" if "apikey" in key else "2/minute")
@cache_busting(
    key_builder=lambda blog, **kw: [
        blog_slug_key(blog.slug),
        blogs_list_key(
            BlogListQuery(skip=0, limit=10, status_filter=blog.status, author_id=blog.author_id),
        ),
        blogs_by_author_key(blog.author_id, PaginationQuery(skip=0, limit=10)),
        blogs_search_tags_key(blog.tags, PaginationQuery(skip=0, limit=10)),
    ],
    namespace="blogs",
)
async def create_blog(
    request: Request,
    response: Response,
    blog: Annotated[
        BlogCreate,
        Body(
            examples={
                "basic": {
                    "summary": "Basic blog creation",
                    "value": {
                        "authorId": "123e4567-e89b-12d3-a456-426614174111",
                        "title": "What to Pack for Your Bali Trip: The Essentials",
                        "summary": "A practical packing guide for Bali",
                        "content": "Bali is wonderful...",
                        "tags": ["bali", "travel"],
                    },
                },
            },
        ),
    ],
    repo: BlogRepoDep,
) -> BlogResponse:
    """
    Create a new blog post.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    blog : BlogCreate
        Blog input payload.
    repo : BlogRepository
        Repository dependency.

    Returns
    -------
    BlogResponse
        Created blog data.

    Raises
    ------
    HTTPException
        If slug already exists.
    """
    try:
        blog_full = BlogSchema.model_validate(blog.model_dump())
        db_blog = await repo.create(blog_full, author_id=blog.author_id)
        return db_blog_to_response(db_blog)
    except DuplicateEntryError as e:
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=e.detail) from e
    except DatabaseError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=e.detail) from e
    except ValueError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get(
    "/by-id/{blog_id}",
    response_class=ORJSONResponse,
    response_model=BlogResponse,
    summary="Get blog by ID",
    description="Retrieve a blog post by its UUID. Increments view count.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "title": "What to Pack for Your Bali Trip: The Essentials",
                        "slug": "what-to-pack-for-your-bali-trip-the-essentials",
                        "viewCount": 1,
                        "tags": ["bali", "travel"],
                        "status": "draft",
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "Blog with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="blogs_get_by_id",
)
@timed("/blogs/by-id")
@limiter.limit(lambda key: "60/minute" if "apikey" in key else "20/minute")
async def get_blog(
    request: Request,
    response: Response,
    blog_id: UUID,
    repo: BlogRepoDep,
) -> BlogResponse:
    """
    Get blog by ID and increment view count.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    blog_id : UUID
        Blog identifier.
    repo : BlogRepository
        Repository dependency.

    Returns
    -------
    BlogResponse
        Blog data.

    Raises
    ------
    HTTPException
        If blog not found.
    """
    db_blog = await repo.increment_view_count(blog_id)
    if not db_blog:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Blog with ID {blog_id} not found",
        )
    return db_blog_to_response(db_blog)


@router.get(
    "/by-slug/{slug}",
    response_class=ORJSONResponse,
    response_model=BlogResponse,
    summary="Get blog by slug",
    description="Retrieve a blog post by its slug.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "title": "What to Pack for Your Bali Trip: The Essentials",
                        "slug": "what-to-pack-for-your-bali-trip-the-essentials",
                        "viewCount": 42,
                        "tags": ["bali", "travel"],
                        "status": "published",
                    },
                },
            },
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "Blog with slug '<slug>' not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="blogs_get_by_slug",
)
@timed("/blogs/by-slug")
@limiter.limit(lambda key: "60/minute" if "apikey" in key else "20/minute")
@cached(
    ttl=3600,
    namespace="blogs",
    key_builder=lambda **kw: blog_slug_key(kw["slug"]),
    response_model=BlogResponse,
)
async def get_blog_by_slug(
    request: Request,
    response: Response,
    slug: str,
    repo: BlogRepoDep,
) -> BlogResponse:
    """
    Get blog by slug.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    slug : str
        Blog slug.
    repo : BlogRepository
        Repository dependency.

    Returns
    -------
    BlogResponse
        Blog data.

    Raises
    ------
    HTTPException
        If blog not found.
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
    response_class=ORJSONResponse,
    response_model=list[BlogListResponse],
    summary="Get all blogs",
    description="Retrieve a paginated list of all blogs with optional filtering.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "title": "What to Pack for Your Bali Trip: The Essentials",
                            "slug": "what-to-pack-for-your-bali-trip-the-essentials",
                            "summary": "A practical packing guide for Bali",
                            "viewCount": 42,
                            "tags": ["bali", "travel"],
                            "status": "published",
                            "createdAt": "2025-01-01",
                            "updatedAt": "2025-01-02",
                            "readingTimeMinutes": 5,
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
    operation_id="blogs_get_all",
)
@timed("/blogs/all")
@limiter.limit(lambda key: "30/minute" if "apikey" in key else "10/minute")
@cached(
    ttl=3600,
    namespace="blogs",
    key_builder=lambda **kw: blogs_list_key(kw["query"]),
)
async def get_blogs(
    request: Request,
    response: Response,
    repo: BlogRepoDep,
    query: BlogQueryListDep,
) -> list[BlogListResponse]:
    """
    Get all blogs with pagination and optional filtering.

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
    status_filter : Literal | None
        Optional status filter.
    author_id : UUID | None
        Optional author ID filter.
    repo : BlogRepository
        Repository dependency.
    query : BlogListQuery
        Aggregated filters and pagination.

    Returns
    -------
    list[BlogListResponse]
        Lightweight blog listing.
    """
    db_blogs = await repo.get_all(
        skip=query.skip,
        limit=query.limit,
        status=query.status_filter,
        author_id=query.author_id,
    )
    return [db_blog_to_list_response(blog) for blog in db_blogs]


@router.get(
    "/by-author-id/{author_id}",
    response_class=ORJSONResponse,
    response_model=list[BlogListResponse],
    summary="Get blogs by author",
    description="Retrieve all blogs by a specific author.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "title": "What to Pack for Your Bali Trip: The Essentials",
                            "slug": "what-to-pack-for-your-bali-trip-the-essentials",
                            "summary": "A practical packing guide for Bali",
                            "viewCount": 42,
                            "tags": ["bali", "travel"],
                            "status": "published",
                            "createdAt": "2025-01-01",
                            "updatedAt": "2025-01-02",
                            "readingTimeMinutes": 5,
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
    operation_id="blogs_get_by_author",
)
@timed("/blogs/by-author-id")
@limiter.limit(lambda key: "30/minute" if "apikey" in key else "10/minute")
@cached(
    ttl=3600,
    namespace="blogs",
    key_builder=lambda **kw: blogs_by_author_key(kw["author_id"], kw["pagination"]),
)
async def get_blogs_by_author(
    request: Request,
    response: Response,
    author_id: UUID,
    repo: BlogRepoDep,
    pagination: Annotated[PaginationQuery, Depends(get_pagination_query)],
) -> list[BlogListResponse]:
    """
    Get all blogs by a specific author.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    author_id : UUID
        Author identifier.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    repo : BlogRepository
        Repository dependency.
    pagination : PaginationQuery
        Pagination controls.

    Returns
    -------
    list[BlogListResponse]
        Blogs by the author.
    """
    db_blogs = await repo.get_by_author(
        author_id,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return [db_blog_to_list_response(blog) for blog in db_blogs]


@router.get(
    "/search/tags",
    response_class=ORJSONResponse,
    response_model=list[BlogListResponse],
    summary="Search blogs by tags",
    description="Search for blogs that match any of the provided tags.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "title": "What to Pack for Your Bali Trip: The Essentials",
                            "slug": "what-to-pack-for-your-bali-trip-the-essentials",
                            "summary": "A practical packing guide for Bali",
                            "viewCount": 42,
                            "tags": ["bali", "travel"],
                            "status": "published",
                            "createdAt": "2025-01-01",
                            "updatedAt": "2025-01-02",
                            "readingTimeMinutes": 5,
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
    operation_id="blogs_search_tags",
)
@timed("/blogs/search/tags")
@limiter.limit(lambda key: "30/minute" if "apikey" in key else "10/minute")
@cached(
    ttl=3600,
    namespace="blogs",
    key_builder=lambda **kw: blogs_search_tags_key(kw["tags"], kw["pagination"]),
)
async def search_blogs_by_tags(
    request: Request,
    response: Response,
    tags: Annotated[list[str], Query(description="Tags to match (any)")],
    repo: BlogRepoDep,
    pagination: Annotated[PaginationQuery, Depends(get_pagination_query)],
) -> list[BlogListResponse]:
    """
    Search blogs by tags.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    tags : list[str]
        Tags to match.
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.
    repo : BlogRepository
        Repository dependency.
    pagination : PaginationQuery
        Pagination controls.

    Returns
    -------
    list[BlogListResponse]
        Blogs matching any of the tags.
    """
    db_blogs = await repo.search_by_tags(
        tags,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    return [db_blog_to_list_response(blog) for blog in db_blogs]


@router.put(
    "/update/{blog_id}",
    response_class=ORJSONResponse,
    response_model=BlogResponse,
    summary="Update blog",
    description="Update blog information. Only provided fields will be updated.",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "title": "Updated: What to Pack for Your Bali Trip",
                        "slug": "what-to-pack-for-your-bali-trip",
                        "viewCount": 43,
                        "tags": ["bali", "travel"],
                        "status": "published",
                    },
                },
            },
        },
        400: {
            "description": "Bad request",
            "content": {"application/json": {"example": {"detail": "Slug already exists"}}},
        },
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "Blog with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="blogs_update",
)
@timed("/blogs/update")
@limiter.limit(lambda key: "20/minute" if "apikey" in key else "5/minute")
@cache_busting(
    key_builder=lambda blog_id, blog_update, deps, **kw: [
        blogs_list_key(BlogListQuery(skip=0, limit=10)),
    ],
    namespace="blogs",
)
async def update_blog(
    request: Request,
    response: Response,
    blog_id: UUID,
    blog_update: Annotated[
        BlogUpdate,
        Body(
            examples={
                "basic": {
                    "summary": "Update blog summary and status",
                    "value": {
                        "summary": "Updated summary",
                        "status": "published",
                    },
                },
            },
        ),
    ],
    deps: Annotated[BlogOpsDeps, Depends()],
) -> BlogResponse:
    """
    Update blog information.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    blog_id : UUID
        Blog identifier.
    blog_update : BlogUpdate
        Partial update payload.
    deps : BlogOpsDeps
        Operation dependencies (repo + current_user).

    Returns
    -------
    BlogResponse
        Updated blog.

    Raises
    ------
    HTTPException
        If blog not found or invalid update.
    """
    try:
        existing = await deps.repo.get_by_id(blog_id)
        if not existing:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Blog with ID {blog_id} not found",
            )
        # Check if user is owner or admin
        check_owner_or_admin(existing.author_id, deps.current_user, "blog")
        db_blog = await deps.repo.update(blog_id, blog_update)
        if not db_blog:
            raise HTTPException(
                status_code=HTTP_404_NOT_FOUND,
                detail=f"Blog with ID {blog_id} not found",
            )
        keys: list[str] = []
        if existing:
            keys.extend(
                [
                    blog_slug_key(existing.slug),
                    blogs_by_author_key(existing.author_id, PaginationQuery(skip=0, limit=10)),
                    blogs_list_key(
                        BlogListQuery(
                            skip=0,
                            limit=10,
                            status_filter=cast(
                                Literal["draft", "published", "archived"] | None,
                                existing.status,
                            ),
                        ),
                    ),
                    blogs_search_tags_key(existing.tags, PaginationQuery(skip=0, limit=10)),
                ],
            )
        keys.extend(
            [
                blog_slug_key(db_blog.slug),
                blogs_by_author_key(db_blog.author_id, PaginationQuery(skip=0, limit=10)),
                blogs_list_key(
                    BlogListQuery(
                        skip=0,
                        limit=10,
                        status_filter=cast(
                            Literal["draft", "published", "archived"] | None,
                            db_blog.status,
                        ),
                    ),
                ),
                blogs_search_tags_key(db_blog.tags, PaginationQuery(skip=0, limit=10)),
            ],
        )
        if keys:
            await get_cache_manager(request).delete(*keys, namespace="blogs")
        return db_blog_to_response(db_blog)
    except ValueError as e:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.delete(
    "/delete/{blog_id}",
    response_class=ORJSONResponse,
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete blog",
    description="Delete a blog post by its UUID.",
    responses={
        204: {"description": "No Content"},
        404: {
            "description": "Not found",
            "content": {
                "application/json": {"example": {"detail": "Blog with ID <uuid> not found"}},
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Rate limit exceeded"}}},
        },
    },
    operation_id="blogs_delete",
)
@timed("/blogs/delete")
@limiter.limit(lambda key: "10/minute" if "apikey" in key else "2/minute")
@cache_busting(
    key_builder=lambda blog_id, **kw: [
        blogs_list_key(BlogListQuery(skip=0, limit=10)),
    ],
    namespace="blogs",
)
async def delete_blog(
    request: Request,
    response: Response,
    blog_id: UUID,
    repo: BlogRepoDep,
    current_user: UserDBDep,
) -> None:
    """
    Delete blog by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    blog_id : UUID
        Blog identifier.
    repo : BlogRepository
        Repository dependency.
    current_user : UserDB
        Authenticated user.

    Raises
    ------
    HTTPException
        If blog not found.
    """
    existing = await repo.get_by_id(blog_id)
    if not existing:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Blog with ID {blog_id} not found",
        )
    # Check if user is owner or admin
    check_owner_or_admin(existing.author_id, current_user, "blog")
    deleted = await repo.delete(blog_id)
    if not deleted:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Blog with ID {blog_id} not found",
        )
    if existing:
        keys = [
            blog_slug_key(existing.slug),
            blogs_by_author_key(existing.author_id, PaginationQuery(skip=0, limit=10)),
            blogs_list_key(
                BlogListQuery(
                    skip=0,
                    limit=10,
                    status_filter=cast(
                        Literal["draft", "published", "archived"] | None,
                        existing.status,
                    ),
                ),
            ),
            blogs_search_tags_key(existing.tags, PaginationQuery(skip=0, limit=10)),
        ]
        await get_cache_manager(request).delete(*keys, namespace="blogs")


@router.post(
    "/bust-list",
    response_class=ORJSONResponse,
    summary="Bust blogs list cache page",
    description="Invalidate cached blogs list page for given filters and pagination.",
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="blogs_bust_list",
)
@timed("/blogs/bust-list")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda **kw: [blogs_list_key(kw["query"])],
    namespace="blogs",
)
async def bust_blogs_list(
    request: Request,
    response: Response,
    query: BlogQueryListDep,
) -> ORJSONResponse:
    """
    Bust blogs list cache page.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    query : BlogListQuery
        Aggregated filters and pagination to build the cache key.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.
    """
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-by-slug",
    response_class=ORJSONResponse,
    summary="Bust cached blog by slug",
    description="Invalidate cached blog detail for a given slug.",
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
    operation_id="blogs_bust_by_slug",
)
@timed("/blogs/bust-by-slug")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda slug, **kw: [blog_slug_key(slug)],
    namespace="blogs",
)
async def bust_blog_by_slug(
    request: Request,
    response: Response,
    slug: str,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-by-author",
    response_class=ORJSONResponse,
    summary="Bust cached blogs by author",
    description="Invalidate cached blogs listing for a given author and pagination.",
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
    operation_id="blogs_bust_by_author",
)
@timed("/blogs/bust-by-author")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda author_id, pagination, **kw: [
        blogs_by_author_key(author_id, pagination),
    ],
    namespace="blogs",
)
async def bust_blogs_by_author(
    request: Request,
    response: Response,
    author_id: UUID,
    pagination: Annotated[PaginationQuery, Depends(get_pagination_query)],
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-by-tags",
    response_class=ORJSONResponse,
    summary="Bust cached blogs by tags",
    description="Invalidate cached blogs search results for given tags and pagination.",
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
    operation_id="blogs_bust_by_tags",
)
@timed("/blogs/bust-by-tags")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda tags, pagination, **kw: [
        blogs_search_tags_key(tags, pagination),
    ],
    namespace="blogs",
)
async def bust_blogs_by_tags(
    request: Request,
    response: Response,
    tags: Annotated[list[str], Query(description="Tags to match (any)")],
    pagination: Annotated[PaginationQuery, Depends(get_pagination_query)],
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-list-multi",
    response_class=ORJSONResponse,
    summary="Bust multiple blogs list cache pages",
    description="Invalidate cached blogs list pages across multiple `limit` values.",
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
    operation_id="blogs_bust_list_multi",
)
@timed("/blogs/bust-list-multi")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda query, limits, **kw: [
        blogs_list_key(
            BlogListQuery(
                skip=query.skip,
                limit=limit,
                status_filter=query.status_filter,
                author_id=query.author_id,
            ),
        )
        for limit in limits
    ],
    namespace="blogs",
)
async def bust_blogs_list_multi(
    request: Request,
    response: Response,
    query: BlogQueryListDep,
    limits: Annotated[list[int], Query(description="List of limit values to invalidate.")],
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-list-grid",
    response_class=ORJSONResponse,
    summary="Bust blogs list pages across limits and skips",
    description="Invalidate cached blogs list pages across multiple `limit` and `skip` values.",
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
    operation_id="blogs_bust_list_grid",
)
@timed("/blogs/bust-list-grid")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda query, grid_query, **kw: [
        blogs_list_key(
            BlogListQuery(
                skip=s,
                limit=limit_value,
                status_filter=query.status_filter,
                author_id=query.author_id,
            ),
        )
        for limit_value in grid_query.limits
        for s in grid_query.skips
    ],
    namespace="blogs",
)
async def bust_blogs_list_grid(
    request: Request,
    response: Response,
    query: BlogQueryListDep,
    grid_query: Annotated[BustListGridQuery, Depends(get_bust_list_grid_query)],
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    return ORJSONResponse(content={"status": "success"})


@router.delete(
    "/bust-all",
    response_class=ORJSONResponse,
    summary="Clear blogs cache namespace",
    description="Clear all cached keys in the blogs namespace.",
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
    operation_id="blogs_bust_all",
)
@timed("/blogs/bust-all")
@limiter.limit("5/minute")
async def bust_blogs_all(
    request: Request,
    response: Response,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    await get_cache_manager(request).clear(namespace="blogs")
    return ORJSONResponse(content={"status": "cleared"})


# =============================================================================
# Media Upload Endpoints
# =============================================================================


@router.post(
    "/{blog_id}/images",
    response_class=ORJSONResponse,
    status_code=HTTP_201_CREATED,
    summary="Upload an image to a blog",
    operation_id="blogs_upload_image",
)
@timed("/blogs/{blog_id}/images")
@limiter.limit("10/minute")
async def upload_blog_image(
    request: Request,
    blog_id: UUID,
    file: UploadFile,
    repo: BlogRepoDep,
    current_user: UserDBDep,
) -> MediaUploadResponse:
    """
    Upload an image to a blog post.

    Only the blog author or admin can upload images.
    Maximum 10 images per blog post.
    """
    db_blog = await repo.get_by_id(blog_id)
    if not db_blog:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Blog not found")

    check_owner_or_admin(db_blog.author_id, current_user)

    current_count = len(db_blog.images_url) if db_blog.images_url else 0
    media_service = MediaService()

    try:
        url = await media_service.upload_blog_image(
            blog_id=str(blog_id),
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

    await repo.add_image(blog_id, url)

    return MediaUploadResponse(url=url, mediaType="image")


@router.post(
    "/{blog_id}/videos",
    response_class=ORJSONResponse,
    status_code=HTTP_201_CREATED,
    summary="Upload a video to a blog",
    operation_id="blogs_upload_video",
)
@timed("/blogs/{blog_id}/videos")
@limiter.limit("5/minute")
async def upload_blog_video(
    request: Request,
    blog_id: UUID,
    file: UploadFile,
    repo: BlogRepoDep,
    current_user: UserDBDep,
) -> MediaUploadResponse:
    """
    Upload a video to a blog post.

    Only the blog author or admin can upload videos.
    Maximum 3 videos per blog post.
    """
    db_blog = await repo.get_by_id(blog_id)
    if not db_blog:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Blog not found")

    check_owner_or_admin(db_blog.author_id, current_user)

    current_count = len(db_blog.videos_url) if db_blog.videos_url else 0
    media_service = MediaService()

    try:
        url = await media_service.upload_blog_video(
            blog_id=str(blog_id),
            file=file,
            current_count=current_count,
        )
    except (
        UnsupportedVideoTypeError,
        VideoTooLargeError,
        MediaLimitExceededError,
    ) as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    await repo.add_video(blog_id, url)

    return MediaUploadResponse(url=url, mediaType="video")


@router.delete(
    "/{blog_id}/media/{media_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete media from a blog",
    operation_id="blogs_delete_media",
)
@timed("/blogs/{blog_id}/media/{media_id}")
@limiter.limit("10/minute")
async def delete_blog_media(
    request: Request,
    blog_id: UUID,
    media_id: str,
    repo: BlogRepoDep,
    current_user: UserDBDep,
) -> None:
    """
    Delete media (image or video) from a blog post.

    Only the blog author or admin can delete media.
    The media_id should be the UUID portion of the media URL.
    """
    db_blog = await repo.get_by_id(blog_id)
    if not db_blog:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Blog not found")

    check_owner_or_admin(db_blog.author_id, current_user)

    # Try to find in images first
    images = db_blog.images_url or []
    media_url_to_delete = None
    is_video = False
    folder = "blog_images"

    for url in images:
        if media_id in str(url):
            media_url_to_delete = str(url)
            break

    # If not found in images, check videos
    if not media_url_to_delete:
        videos = db_blog.videos_url or []
        folder = "blog_videos"
        for url in videos:
            if media_id in str(url):
                media_url_to_delete = str(url)
                is_video = True
                break

    if not media_url_to_delete:
        raise HTTPException(
            status_code=HTTP_404_NOT_FOUND,
            detail=f"Media with ID {media_id} not found in blog",
        )

    # Delete from storage
    media_service = MediaService()
    await media_service.delete_media(
        folder=folder,
        entity_id=str(blog_id),
        media_id=media_id,
    )

    # Remove from database
    if is_video:
        await repo.remove_video(blog_id, media_url_to_delete)
    else:
        await repo.remove_image(blog_id, media_url_to_delete)
