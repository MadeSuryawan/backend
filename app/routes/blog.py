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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import getLogger
from typing import Annotated, Literal, Never, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, ValidationError
from starlette.responses import Response
from starlette.status import (
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from app.decorators.caching import cache_busting, cached, get_cache_manager
from app.decorators.metrics import timed
from app.dependencies import (
    AdminUserDep,
    BlogListQuery,
    BlogQueryListDep,
    BlogRepoDep,
    UserDBDep,
    VerifiedUserDep,
    check_owner_or_admin,
)
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

    blog_id: UUID
    repo: BlogRepoDep
    current_user: UserDBDep
    verified_user: VerifiedUserDep


@dataclass(frozen=True)
class BlogCreateDeps:
    """Dependencies for blog creation (no blog_id required)."""

    repo: BlogRepoDep
    current_user: UserDBDep
    verified_user: VerifiedUserDep


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


# =============================================================================
# Helper Functions
# =============================================================================


def _404_not_found(value: UUID | str, by: str = "id") -> Never:
    """
    Raise a 404 HTTPException for a missing blog.

    Parameters
    ----------
    value : UUID | str
        The value that was not found.
    by : str
        The field name used for looking up the blog (default: "id").

    Raises
    ------
    HTTPException
        Always raises 404 Not Found.

    """
    raise HTTPException(status_code=404, detail=f"Blog with {by} '{value}' not found")


async def _get_blog_or_404(blog_id: UUID, repo: BlogRepoDep) -> BlogDB:
    """
    Get a blog by ID or raise a 404 error.

    Parameters
    ----------
    blog_id : UUID
        The ID of the blog to retrieve.
    repo : BlogRepoDep
        The blog repository.

    Returns
    -------
    BlogDB
        The blog entity.

    Raises
    ------
    HTTPException
        404 if the blog is not found.

    """
    if not (blog := await repo.get_by_id(blog_id)):
        _404_not_found(blog_id, by="id")
    return blog


def _validate_blog_response(schema: type[BaseModel], db_blog: BlogDB) -> BaseModel:
    """
    Validate a blog response model.

    Parameters
    ----------
    schema : BaseModel
        The blog response model to validate.
    db_blog : BlogDB
        The database blog entity to validate.

    Returns
    -------
    BaseModel
        The validated blog response model.

    """
    _dict = response_datetime(db_blog)
    try:
        response = schema.model_validate(_dict, from_attributes=True)
    except ValidationError as e:
        mssg = f"Validation error converting blog to response model: {e}"
        logger.exception("Validation error converting blog to response model")
        raise ValueError(mssg) from e

    return response


def get_pagination_query(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 10,
) -> PaginationQuery:
    """
    Dependency to construct `PaginationQuery` from query parameters.

    Parameters
    ----------
    skip : int
        Number of records to skip.
    limit : int
        Maximum number of records to return.

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

    Parameters
    ----------
    limits : list[int]
        List of limit values to invalidate.
    skips : list[int]
        List of skip values to invalidate.

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


async def delete_cache_keys(
    existing: BlogDB,
    db_blog: BlogDB | None,
    request: Request,
) -> None:
    """
    Delete cache keys for a blog.

    Parameters
    ----------
    existing : BlogDB
        Existing blog entity.
    db_blog : BlogDB | None
        Database blog entity.
    request : Request
        Request object.

    """
    keys: list[str] = []
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
    if db_blog:
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


# =============================================================================
# Blog Endpoints
# =============================================================================


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
            "content": {
                "application/json": {
                    "example": {
                        "detail": "A blog with this URL slug already exists. Please choose a different title or slug.",
                    },
                },
            },
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
    deps: Annotated[BlogCreateDeps, Depends()],
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
    deps : BlogCreateDeps
        Operation dependencies (repo + current_user).

    Returns
    -------
    BlogResponse
        Created blog data.

    Raises
    ------
    HTTPException
        If slug already exists.

    """
    check_owner_or_admin(blog.author_id, deps.current_user, "create_blog")
    try:
        blog_full = BlogSchema.model_validate(blog.model_dump())
        db_blog = await deps.repo.create(blog_full, author_id=blog.author_id)
        return cast(BlogResponse, _validate_blog_response(BlogResponse, db_blog))
    except DuplicateEntryError as e:
        logger.exception(f"Duplicate slug '{blog.slug}' detected on blog creation")
        raise HTTPException(status_code=HTTP_409_CONFLICT, detail=e.detail) from e
    except DatabaseError as e:
        logger.exception("Database error on blog creation")
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail=e.detail) from e
    except ValueError as e:
        logger.exception("Value error on blog creation")
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
    if not (db_blog := await repo.increment_view_count(blog_id)):
        _404_not_found(blog_id, by="id")
    return cast(BlogResponse, _validate_blog_response(BlogResponse, db_blog))


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
    if not (db_blog := await repo.get_by_slug(slug)):
        _404_not_found(slug, by="slug")
    return cast(BlogResponse, _validate_blog_response(BlogResponse, db_blog))


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
    repo : BlogRepoDep
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
    return [
        cast(BlogListResponse, _validate_blog_response(BlogListResponse, blog)) for blog in db_blogs
    ]


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
    repo : BlogRepoDep
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
    return [
        cast(BlogListResponse, _validate_blog_response(BlogListResponse, blog)) for blog in db_blogs
    ]


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
    repo : BlogRepoDep
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
    return [
        cast(BlogListResponse, _validate_blog_response(BlogListResponse, blog)) for blog in db_blogs
    ]


@router.patch(
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
            "content": {
                "application/json": {
                    "example": {
                        "detail": "A blog with this URL slug already exists. Please choose a different title or slug.",
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
    blog_update : BlogUpdate
        Partial update payload.
    deps : BlogOpsDeps
        Operation dependencies (blog_id + repo + current_user).

    Returns
    -------
    BlogResponse
        Updated blog.

    Raises
    ------
    HTTPException
        If blog not found or invalid update.

    """
    existing = await _get_blog_or_404(deps.blog_id, deps.repo)
    check_owner_or_admin(existing.author_id, deps.current_user, "update_blog")

    if not (db_blog := await deps.repo.update(deps.blog_id, blog_update)):
        _404_not_found(deps.blog_id, by="id")

    await delete_cache_keys(existing, db_blog, request)
    return cast(BlogResponse, _validate_blog_response(BlogResponse, db_blog))


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
    key_builder=lambda *args, **kwargs: [
        blogs_list_key(BlogListQuery(skip=0, limit=10)),
    ],
    namespace="blogs",
)
async def delete_blog(
    request: Request,
    response: Response,
    deps: Annotated[BlogOpsDeps, Depends()],
) -> Response:
    """
    Delete blog by ID.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    deps : BlogOpsDeps
        Operation dependencies (blog_id + repo + current_user).

    Raises
    ------
    HTTPException
        If blog not found.

    """
    existing = await _get_blog_or_404(deps.blog_id, deps.repo)
    check_owner_or_admin(existing.author_id, deps.current_user, "delete_blog")

    # [NEW] Cleanup all associated media
    media_service = MediaService()
    try:
        if existing.images_url:
            await media_service.delete_all_media("blog_images", str(deps.blog_id))
        if existing.videos_url:
            await media_service.delete_all_media("blog_videos", str(deps.blog_id))
    except Exception:
        logger.exception("Failed to cleanup media for blog %s during deletion", deps.blog_id)

    if not await deps.repo.delete(deps.blog_id):
        _404_not_found(deps.blog_id, by="id")

    await delete_cache_keys(existing, None, request)
    logger.info("Blog '%s' deleted by user '%s'", existing.title, deps.current_user.email)
    return Response(status_code=HTTP_204_NO_CONTENT)


# =============================================================================
# Cache Busting Endpoints
# =============================================================================


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
    admin_user: AdminUserDep,
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
    admin_user : AdminUserDep
        Admin user dependency.

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
    """
    Invalidate cached blog detail for a given slug.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    slug : str
        Blog slug to invalidate.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    """
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
    """
    Invalidate cached blogs listing for a given author and pagination.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    author_id : UUID
        Author identifier.
    pagination : PaginationQuery
        Pagination controls.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    """
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
    """
    Invalidate cached blogs search results for given tags and pagination.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    tags : list[str]
        Tags to match.
    pagination : PaginationQuery
        Pagination controls.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    """
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
    """
    Invalidate cached blogs list pages across multiple limits.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    query : BlogListQuery
        Aggregated filters and initial pagination.
    limits : list[int]
        List of limit values to invalidate.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    """
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
    """
    Invalidate cached blogs list pages across multiple limits and skips.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    query : BlogListQuery
        Aggregated filters.
    grid_query : BustListGridQuery
        Grid of limits and skips to invalidate.
    admin_user : AdminUserDep
        Admin user dependency for authorization.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    """
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
    """
    Clear all cached keys in the blogs namespace.

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
        Status message indicating success.

    """
    await get_cache_manager(request).clear(namespace="blogs")
    return ORJSONResponse(content={"status": "cleared"})


# =============================================================================
# Media Helper Functions
# =============================================================================

MediaUploadFunc = Callable[[str, UploadFile, int], Awaitable[tuple[str, str]]]
RepoAddFunc = Callable[[UUID, str], Awaitable[None]]
UPLOAD_EXCEPTIONS = (
    UnsupportedImageTypeError,
    ImageTooLargeError,
    InvalidImageError,
    ImageProcessingError,
    MediaLimitExceededError,
    UnsupportedVideoTypeError,
    VideoTooLargeError,
)


def _validate_media_response(media_id: str, url: str, media_type: str) -> MediaUploadResponse:
    """
    Create a validated MediaUploadResponse from the given parameters.

    Parameters
    ----------
    media_id : str
        ID of the uploaded media.
    url : str
        URL of the uploaded media.
    media_type : str
        Type of media (image/video).

    Returns
    -------
    MediaUploadResponse
        Validated media upload response.

    Raises
    ------
    ValueError
        If validation fails.

    """
    try:
        _dict = {"media_id": media_id, "url": url, "media_type": media_type}
        response = MediaUploadResponse.model_validate(_dict, from_attributes=True)
    except ValidationError as e:
        logger.exception("Validation error in media upload response")
        detail = f"Validation error in media upload response: {e}"
        raise ValueError(detail) from e
    return response


async def _upload_media(
    db_blog: BlogDB,
    repo: BlogRepoDep,
    blog_id: UUID,
    file: UploadFile,
    media_type: Literal["image", "video"],
) -> MediaUploadResponse:
    """
    Upload media (image/video) to a blog post.

    Parameters
    ----------
    db_blog : BlogDB
        Database blog entity.
    repo : BlogRepoDep
        Blog repository dependency.
    blog_id : UUID
        Blog identifier.
    file : UploadFile
        File to upload.
    media_type : Literal["image", "video"]
        Type of media being uploaded.

    Returns
    -------
    MediaUploadResponse
        Validated media upload metadata.

    Raises
    ------
    HTTPException
        If the upload fails or limits are exceeded.

    """
    current_count = 0
    if url_list := getattr(db_blog, f"{media_type}s_url"):
        current_count = len(url_list)

    media_service = MediaService()
    media_func: MediaUploadFunc = getattr(media_service, f"upload_blog_{media_type}")
    repo_func: RepoAddFunc = getattr(repo, f"add_{media_type}")

    try:
        media_id, url = await media_func(f"{blog_id}", file, current_count)
    except UPLOAD_EXCEPTIONS as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    await repo_func(blog_id, url)

    return _validate_media_response(media_id, url, media_type)


def _get_folder(
    db_blog: BlogDB,
    media_id: str,
) -> str:
    """
    Get the folder name (blog_images or blog_videos) based on the media ID.

    Parameters
    ----------
    db_blog : BlogDB
        Database blog entity.
    media_id : str
        Identifier of the media to delete.

    Returns
    -------
    str
        Folder name (blog_images or blog_videos).
    """
    if db_blog.images_url and any(f"/{media_id}" in url for url in db_blog.images_url):
        return "blog_images"
    if db_blog.videos_url and any(f"/{media_id}" in url for url in db_blog.videos_url):
        return "blog_videos"
    return ""


async def _delete_media(
    folder: str,
    blog_id: UUID,
    media_id: str,
) -> None:
    """
    Delete media (image/video) from a blog post.

    Parameters
    ----------
    folder : str
        Folder name (blog_images or blog_videos).
    blog_id : UUID
        Blog identifier.
    media_id : str
        Identifier of the media to delete.

    Returns
    -------
    dict[str, str]
        Status message indicating which folder was affected.

    Raises
    ------
    HTTPException
        If media is not found or deletion fails.

    """
    media_service = MediaService()
    deleted = await media_service.delete_media(
        folder=folder,
        entity_id=str(blog_id),
        media_id=media_id,
    )
    if not deleted:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")


async def _cleanup_media(
    folder: str,
    repo: BlogRepoDep,
    blog_id: UUID,
    media_id: str,
) -> None:
    """
    Cleanup all media associated with a blog post.

    Parameters
    ----------
    folder : str
        Folder name (blog_images or blog_videos).
    repo : BlogRepoDep
        Blog repository dependency.
    blog_id : UUID
        Blog identifier.
    media_id : str
        Identifier of the media to delete.

    Raises
    ------
    HTTPException
        If media is not found or deletion fails.

    """

    if folder == "blog_images":
        removed = await repo.remove_image_by_media_id(
            blog_id,
            media_id,
        )
    else:
        removed = await repo.remove_video_by_media_id(
            blog_id,
            media_id,
        )

    if not removed:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")


# =============================================================================
# Media Endpoints
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
    response: Response,
    file: UploadFile,
    deps: Annotated[BlogOpsDeps, Depends()],
) -> MediaUploadResponse:
    """
    Upload an image to a blog post.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    file : UploadFile
        Image file to upload.
    deps : BlogOpsDeps
        Operation dependencies (blog_id + repo + current_user).

    Returns
    -------
    MediaUploadResponse
        Validated media upload metadata.

    Notes
    -----
    - Only the blog author or admin can upload images.
    - Maximum 10 images per blog post.

    """
    db_blog = await _get_blog_or_404(deps.blog_id, deps.repo)

    check_owner_or_admin(db_blog.author_id, deps.current_user)

    return await _upload_media(db_blog, deps.repo, deps.blog_id, file, "image")


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
    response: Response,
    file: UploadFile,
    deps: Annotated[BlogOpsDeps, Depends()],
) -> MediaUploadResponse:
    """
    Upload a video to a blog post.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    file : UploadFile
        Video file to upload.
    deps : BlogOpsDeps
        Operation dependencies (blog_id + repo + current_user).

    Returns
    -------
    MediaUploadResponse
        Validated media upload metadata.

    Notes
    -----
    - Only the blog author or admin can upload videos.
    - Maximum 3 videos per blog post.

    """
    db_blog = await _get_blog_or_404(deps.blog_id, deps.repo)

    check_owner_or_admin(db_blog.author_id, deps.current_user)

    return await _upload_media(db_blog, deps.repo, deps.blog_id, file, "video")


@router.delete(
    "/{blog_id}/media/{media_id}",
    status_code=HTTP_204_NO_CONTENT,
    summary="Delete media from a blog",
    operation_id="blogs_delete_media",
    response_class=ORJSONResponse,
)
@timed("/blogs/{blog_id}/media")
@limiter.limit("10/minute")
async def delete_blog_media(
    request: Request,
    response: Response,
    media_id: str,
    deps: Annotated[BlogOpsDeps, Depends()],
) -> ORJSONResponse:
    """
    Delete an image/video from a blog post.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Response object for middleware/decorators.
    media_id : str
        Identifier of the media to delete.
    deps : BlogOpsDeps
        Operation dependencies (blog_id + repo + current_user).

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    """
    db_blog = await _get_blog_or_404(deps.blog_id, deps.repo)

    check_owner_or_admin(db_blog.author_id, deps.current_user)

    if not (folder := _get_folder(db_blog, media_id)):
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Media not found")

    await _delete_media(folder, deps.blog_id, media_id)
    await _cleanup_media(folder, deps.repo, deps.blog_id, media_id)

    return ORJSONResponse(content={"status": f"{folder} deleted"})
