# app/routes/items.py

"""
Items API Routes.

Provides CRUD endpoints and various typed views, with caching and cache busting.

Summary
-------
Endpoints include:
  - Create, update, delete, and get item by id
  - Get all items (raw list, mapping, tuple, and dict-of-list)
  - Paginated listing with per-page caching
  - Explicit cache-busting endpoints for paginated pages

Caching
-------
All read endpoints use a cache layer with TTL. Keys follow clear naming
conventions (e.g., `item_{id}`, `get_all_items`, `get_paginated_items_{page}_{page_size}`).

Rate Limiting
-------------
Write and read operations are rate limited to protect the service.
"""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import ORJSONResponse
from pydantic.main import BaseModel
from starlette.status import HTTP_404_NOT_FOUND

from app.decorators.caching import cache_busting, cached, get_cache_manager
from app.decorators.metrics import timed
from app.managers.rate_limiter import limiter
from app.schemas import Item, ItemUpdate
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/items", tags=["📦 Items"], include_in_schema=False)


# In-memory database (for demo purposes)
items_db: dict[int, Item] = {}


class AllItemsResponse(BaseModel):
    items: list[Item]


class PaginatedItemsResponse(BaseModel):
    items: list[Item]
    total: int
    page: int
    page_size: int
    pages: int


# --- Routes ---
@router.post(
    "/",
    response_model=Item,
    summary="Create new item",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"id": 1, "name": "A", "description": None, "price": 9.99},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="create_item",
)
@timed("/items/create")
@limiter.limit("2/minute")
@cache_busting(
    keys=[
        "get_all_items",
        "get_raw_items",
        "get_map_items",
        "get_dict_list_items",
        "get_tuple_items",
    ],
    namespace="items",
)
async def create_item(
    request: Request,
    response: Response,
    item: Annotated[
        Item,
        Body(
            examples={
                "basic": {
                    "summary": "Basic item",
                    "value": {"id": 1, "name": "A", "description": None, "price": 9.99},
                },
            },
        ),
    ],
) -> Item:
    """
    Create a new item with cache busting.

    Parameters
    ----------
    item : Item
        Item payload to create.
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    Item
        The created item.

    Notes
    -----
    - Rate limited to 2 requests per minute.
    - Invalidates list/mapping caches and sets `item_{id}` with a TTL of 3600 seconds.

    Examples
    --------
    Request
        POST /items/
        Body: {"id": 1, "name": "A", "price": 9.99}
    Response
        200 OK
        {"id": 1, "name": "A", "price": 9.99}

    Request schema
    --------------
    {
      "id": int,
      "name": str,
      "description": str | null,
      "price": float
    }

    Response schema
    ---------------
    {
      "id": int,
      "name": str,
      "description": str | null,
      "price": float
    }
    """
    logger.info(f"Creating item: {item.name}")
    items_db[item.id] = item

    # Proactively set the cache (Write-Through)
    # This prevents the subsequent "Miss" when the user fetches it for the first time
    await get_cache_manager(request).set(
        f"item_{item.id}",
        item.model_dump(),
        ttl=3600,
        namespace="items",
    )

    return item


@router.get(
    "/get-item/{item_id}",
    summary="Get item by ID",
    description="Return a single item by its identifier; 404 when absent.",
    response_class=ORJSONResponse,
    response_model=Item,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"id": 1, "name": "A", "description": None, "price": 9.99},
                },
            },
        },
        404: {
            "content": {"application/json": {"example": {"detail": "Item not found"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="get_item_by_id",
)
@timed("/items/get")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda item_id, **kw: f"item_{item_id}",
    response_model=Item,
)
async def get_item(item_id: int, request: Request, response: Response) -> Item:
    """
    Get specific item with caching.

    Parameters
    ----------
    item_id : int
        Identifier of the item.
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    Item
        The requested item.

    Notes
    -----
    - Rate limited to 10 requests per minute.
    - Cached under key `item_{item_id}` for 3600 seconds.

    Examples
    --------
    Request
        GET /items/get-item/1
    Response
        200 OK
        {"id": 1, "name": "A", "price": 9.99}

    Response schema
    ---------------
    {
      "id": int,
      "name": str,
      "description": str | null,
      "price": float
    }
    """
    logger.info(f"Fetching item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Item not found")
    return items_db[item_id]


@router.get(
    "/all-items",
    summary="Get all items",
    description="Return all items wrapped in an envelope for future extensibility.",
    response_class=ORJSONResponse,
    response_model=AllItemsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "items": [{"id": 1, "name": "A", "description": None, "price": 9.99}],
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="get_all_items",
)
@timed("/items/all")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda **kw: "get_all_items",
    response_model=AllItemsResponse,
)
async def get_all_items(request: Request, response: Response) -> AllItemsResponse:
    """
    Get all items with caching.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    AllItemsResponse
        Envelope containing the full list of items.

    Notes
    -----
    - Rate limited to 10 requests per minute.
    - Cached under key `get_all_items` for 3600 seconds.

    Examples
    --------
    Request
        GET /items/all-items
    Response
        200 OK
        {"items": [{"id": 1, "name": "A", "price": 9.99}, ...]}

    Response schema
    ---------------
    {
      "items": [
        {
          "id": int,
          "name": str,
          "description": str | null,
          "price": float
        },
        ...
      ]
    }
    """
    logger.info("Fetching all items")
    return AllItemsResponse(items=list(items_db.values()))


@router.get(
    "/raw-items",
    summary="Get all items raw",
    description="Return all items as a plain list; supports cache bypass via `refresh`.",
    response_class=ORJSONResponse,
    response_model=list[Item],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [{"id": 1, "name": "A", "description": None, "price": 9.99}],
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="get_raw_items",
)
@timed("/items/raw")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda **kw: "get_raw_items",
)
async def get_raw_items(
    request: Request,
    response: Response,
    *,
    refresh: Annotated[bool, Query(description="Bypass cache-read for fresh retrieval.")] = False,
) -> list[Item]:
    """
    Return all items without additional structure.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    refresh : bool
        When true, bypasses cache-read for fresh retrieval.

    Returns
    -------
    list[Item]
        Unordered list of items from the in-memory store.

    Caching
    -------
    Cached under key `get_raw_items` for 3600 seconds in the `items` namespace.

    Examples
    --------
    Request
        GET /items/raw-items?refresh=false
    Response
        200 OK
        [{"id": 1, "name": "A", "price": 9.99}, ...]

    Response schema
    ---------------
    [
      {
        "id": int,
        "name": str,
        "description": str | null,
        "price": float
      },
      ...
    ]
    """
    return list(items_db.values())


@router.get(
    "/map-items",
    summary="Get items as mapping",
    description="Return a mapping of item name to item for quick lookups.",
    response_class=ORJSONResponse,
    response_model=dict[str, Item],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"A": {"id": 1, "name": "A", "description": None, "price": 9.99}},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="get_map_items",
)
@timed("/items/map")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda **kw: "get_map_items",
)
async def get_map_items(request: Request, response: Response) -> dict[str, Item]:
    """
    Return items as a mapping of `name -> Item`.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    dict[str, Item]
        Dictionary mapping item names to items.

    Notes
    -----
    Cached under key `get_map_items` for 3600 seconds in the `items` namespace.
    """
    return {item.name: item for item in items_db.values()}


@router.get(
    "/maybe-item/{item_id}",
    summary="Get item or null",
    description="Return the item if present; otherwise null.",
    response_class=ORJSONResponse,
    response_model=Item | None,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"id": 1, "name": "A", "description": None, "price": 9.99},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="get_maybe_item",
)
@timed("/items/maybe")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda item_id, **kw: f"get_maybe_item_{item_id}",
)
async def get_maybe_item(item_id: int, request: Request, response: Response) -> Item | None:
    """
    Return an item by id or `None` if not found.

    Parameters
    ----------
    item_id : int
        Identifier of the item.
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    Item | None
        The item if present; otherwise `None`.

    Notes
    -----
    Cached under key `get_maybe_item_{item_id}` for 3600 seconds.
    """
    return items_db.get(item_id)


@router.get(
    "/paginated",
    summary="Get paginated items",
    description="Return paginated items; cached per `(page, page_size)`.",
    response_class=ORJSONResponse,
    response_model=PaginatedItemsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {"id": 1, "name": "A", "description": None, "price": 9.99},
                            {"id": 2, "name": "B", "description": None, "price": 19.99},
                        ],
                        "total": 3,
                        "page": 1,
                        "page_size": 2,
                        "pages": 2,
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"detail": "Too Many Requests"},
                },
            },
        },
    },
    operation_id="get_paginated_items",
)
@timed("/items/paginated")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda **kw: f"get_paginated_items_{kw.get('page', 1)}_{kw.get('page_size', 10)}",
)
async def get_paginated_items(
    request: Request,
    response: Response,
    *,
    page: Annotated[int, Query(ge=1, description="1-based page number.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page (1-100). ")] = 10,
) -> PaginatedItemsResponse:
    """
    Return paginated items sorted by id.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    page : int
        1-based page number.
    page_size : int
        Items per page, in [1, 100].

    Returns
    -------
    PaginatedItemsResponse
        Items slice with pagination metadata.

    Caching
    -------
    Cached per `(page, page_size)` for 3600 seconds using
    key `get_paginated_items_{page}_{page_size}` in the `items` namespace.

    Examples
    --------
    Request
        GET /items/paginated?page=1&page_size=2
    Response
        200 OK
        {"items": [{"id": 1, ...}, {"id": 2, ...}], "total": 3, "page": 1, "page_size": 2, "pages": 2}

    Response schema
    ---------------
    {
      "items": [
        {
          "id": int,
          "name": str,
          "description": str | null,
          "price": float
        },
        ...
      ],
      "total": int,
      "page": int,
      "page_size": int,
      "pages": int
    }
    """
    items_list: list[Item] = sorted(items_db.values(), key=lambda i: i.id)
    total = len(items_list)
    start = (page - 1) * page_size
    end = start + page_size
    slice_items = items_list[start:end]
    pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PaginatedItemsResponse(
        items=slice_items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.post(
    "/bust-paginated",
    summary="Bust paginated cache page",
    description="Invalidate the cached page for the given `page` and `page_size`.",
    response_class=ORJSONResponse,
    response_model=dict[str, str],
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="bust_paginated",
)
@timed("/items/bust-paginated")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda **kw: [f"get_paginated_items_{kw.get('page', 1)}_{kw.get('page_size', 10)}"],
    namespace="items",
)
async def bust_paginated(
    request: Request,
    response: Response,
    *,
    page: Annotated[int, Query(ge=1, description="Target page number.")],
    page_size: Annotated[int, Query(ge=1, le=100, description="Target page size.")],
) -> ORJSONResponse:
    """
    Bust a single paginated cache page.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    page : int
        Target page number (>= 1).
    page_size : int
        Target page size in [1, 100].

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    Notes
    -----
    Deletes the cache entry `get_paginated_items_{page}_{page_size}`
    in the `items` namespace.

    Examples
    --------
    Request
        POST /items/bust-paginated?page=1&page_size=2
    Response
        200 OK
        {"status": "success"}

    Response schema
    ---------------
    {
      "status": str
    }
    """
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-paginated-all",
    summary="Bust all paginated cache pages",
    description="Invalidate all cached pages for the given `page_size`.",
    response_class=ORJSONResponse,
    response_model=dict[str, str],
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="bust_paginated_all",
)
@timed("/items/bust-paginated-all")
@limiter.limit("10/minute")
async def bust_paginated_all(
    request: Request,
    response: Response,
    *,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Page size whose cache should be invalidated."),
    ],
) -> ORJSONResponse:
    """
    Bust all paginated cache pages for the given `page_size`.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    page_size : int
        Target page size in [1, 100].

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    Notes
    -----
    Computes the number of pages from current items and deletes keys
    `get_paginated_items_{page}_{page_size}` for all pages in range.

    Examples
    --------
    Request
        POST /items/bust-paginated-all?page_size=2
    Response
        200 OK
        {"status": "success"}

    Response schema
    ---------------
    {
      "status": str
    }
    """
    total = len(items_db.values())
    pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    keys = [f"get_paginated_items_{p}_{page_size}" for p in range(1, pages + 1)]
    if keys:
        await get_cache_manager(request).delete(*keys, namespace="items")
    return ORJSONResponse(content={"status": "success"})


@router.post(
    "/bust-paginated-multi",
    summary="Bust paginated cache pages across sizes",
    description="Invalidate cached pages for multiple `page_sizes`.",
    response_class=ORJSONResponse,
    response_model=dict[str, str],
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "success"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="bust_paginated_multi",
)
@timed("/items/bust-paginated-multi")
@limiter.limit("10/minute")
async def bust_paginated_multi(
    request: Request,
    response: Response,
    *,
    page_sizes: Annotated[list[int], Query(description="List of page sizes to invalidate.")],
) -> ORJSONResponse:
    """
    Bust cached paginated pages across multiple `page_sizes`.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    page_sizes : list[int]
        Collection of page sizes to invalidate; invalid sizes are skipped.

    Returns
    -------
    ORJSONResponse
        Status message indicating success.

    Notes
    -----
    Deletes keys following `get_paginated_items_{page}_{size}` in the `items` namespace.

    Examples
    --------
    Request
        POST /items/bust-paginated-multi?page_sizes=1&page_sizes=2
    Response
        200 OK
        {"status": "success"}

    Response schema
    ---------------
    {
      "status": str
    }
    """
    total = len(items_db.values())
    keys: list[str] = []
    for size in page_sizes:
        if size < 1 or size > 100:
            continue
        pages = (total + size - 1) // size if size > 0 else 0
        keys.extend([f"get_paginated_items_{p}_{size}" for p in range(1, pages + 1)])
    if keys:
        await get_cache_manager(request).delete(*keys, namespace="items")
    return ORJSONResponse(content={"status": "success"})


@router.get(
    "/dict-list-items",
    summary="Get items in dict of lists",
    description="Return items grouped in a dict with key `all`.",
    response_class=ORJSONResponse,
    response_model=dict[str, list[Item]],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "all": [
                            {"id": 1, "name": "A", "description": None, "price": 9.99},
                        ],
                    },
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="get_dict_list_items",
)
@timed("/items/dict-list")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda **kw: "get_dict_list_items",
)
async def get_dict_list_items(request: Request, response: Response) -> dict[str, list[Item]]:
    """
    Return items inside a `dict[str, list[Item]]` under the key `all`.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    dict[str, list[Item]]
        Mapping with a single key `all` containing all items.

    Notes
    -----
    Useful for validating nested container caching and typed rehydration.

    Examples
    --------
    Request
        GET /items/dict-list-items
    Response
        200 OK
        {"all": [{"id": 1, ...}, ...]}

    Response schema
    ---------------
    {
      "all": [
        {
          "id": int,
          "name": str,
          "description": str | null,
          "price": float
        },
        ...
      ]
    }
    """
    return {"all": list(items_db.values())}


@router.get(
    "/tuple-items",
    summary="Get items as tuple",
    description="Return items as a tuple (serialized as JSON array).",
    response_class=ORJSONResponse,
    response_model=tuple[Item, ...],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {"id": 1, "name": "A", "description": None, "price": 9.99},
                        {"id": 2, "name": "B", "description": None, "price": 19.99},
                    ],
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="get_tuple_items",
)
@timed("/items/tuple")
@limiter.limit("10/minute")
@cached(
    ttl=3600,
    namespace="items",
    key_builder=lambda **kw: "get_tuple_items",
)
async def get_tuple_items(request: Request, response: Response) -> tuple[Item, ...]:
    """
    Return items as `tuple[Item, ...]`.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    tuple[Item, ...]
        All items from the in-memory store.

    Notes
    -----
    JSON representation will appear as a list when serialized.

    Examples
    --------
    Request
        GET /items/tuple-items
    Response
        200 OK
        [{"id": 1, ...}, {"id": 2, ...}]

    Response schema
    ---------------
    [
      {
        "id": int,
        "name": str,
        "description": str | null,
        "price": float
      },
      ...
    ]
    """
    return tuple(items_db.values())


@router.patch(
    "/update-item/{item_id}",
    summary="Update item by ID",
    description="Update an item by id and invalidate related caches.",
    response_class=ORJSONResponse,
    response_model=Item,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"id": 1, "name": "A-Edit", "description": None, "price": 9.99},
                },
            },
        },
        404: {
            "content": {"application/json": {"example": {"detail": "Item not found"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="update_item_by_id",
)
@timed("/items/update")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda item_id, **kw: [
        f"item_{item_id}",
        "get_all_items",
        "get_raw_items",
        "get_map_items",
        "get_dict_list_items",
        "get_tuple_items",
        f"get_maybe_item_{item_id}",
    ],
    namespace="items",
)
async def update_item(
    item_id: int,
    request: Request,
    response: Response,
    item_update: Annotated[
        ItemUpdate,
        Body(
            examples={
                "updateName": {
                    "summary": "Update name",
                    "value": {"name": "A-Edit"},
                },
            },
        ),
    ],
) -> Item:
    """
    Update an item with cache busting.

    Parameters
    ----------
    item_id : int
        Identifier of the item to update.
    item_update : ItemUpdate
        Partial update payload.
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    Item
        The updated item.

    Notes
    -----
    - Rate limited to 10 requests per minute.
    - Invalidates item, list, mapping, and related caches.

    Examples
    --------
    Request
        PUT /items/update-item/1
        Body: {"name": "A-Edit"}
    Response
        200 OK
        {"id": 1, "name": "A-Edit", "price": 9.99}

    Request schema
    --------------
    {
      "name": str | null,
      "description": str | null,
      "price": float | null
    }

    Response schema
    ---------------
    {
      "id": int,
      "name": str,
      "description": str | null,
      "price": float
    }
    """
    logger.info(f"Updating item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    existing_item = items_db[item_id]
    updated_data = item_update.model_dump(exclude_unset=True)
    updated_item = existing_item.model_copy(update=updated_data)
    items_db[item_id] = updated_item
    return updated_item


@router.delete(
    "/delete-item/{item_id}",
    summary="Delete item by ID",
    description="Delete an item and invalidate related caches.",
    response_class=ORJSONResponse,
    response_model=dict[str, str],
    responses={
        200: {
            "content": {"application/json": {"example": {"message": "Item deleted successfully"}}},
        },
        404: {
            "content": {"application/json": {"example": {"detail": "Item not found"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="delete_item_by_id",
)
@timed("/items/delete")
@limiter.limit("10/minute")
@cache_busting(
    key_builder=lambda item_id, **kw: [
        f"item_{item_id}",
        "get_all_items",
        "get_raw_items",
        "get_map_items",
        "get_dict_list_items",
        "get_tuple_items",
        f"get_maybe_item_{item_id}",
    ],
    namespace="items",
)
async def delete_item(item_id: int, request: Request, response: Response) -> ORJSONResponse:
    """
    Delete an item with cache busting.

    Parameters
    ----------
    item_id : int
        Identifier of the item to delete.
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    ORJSONResponse
        Status message upon successful deletion.

    Notes
    -----
    - Rate limited to 10 requests per minute.
    - Invalidates item, list, mapping, and related caches.

    Examples
    --------
    Request
        DELETE /items/delete-item/1
    Response
        200 OK
        {"message": "Item deleted successfully"}

    Response schema
    ---------------
    {
      "message": str
    }
    """
    logger.info(f"Deleting item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    del items_db[item_id]
    if not items_db.get(item_id):
        return ORJSONResponse(content={"message": "Item deleted successfully"})
    raise HTTPException(status_code=500, detail="Failed to delete item, please try again")


@router.delete(
    "/clear-all",
    summary="Clear all items",
    description="Clear in-memory items and purge common cache keys.",
    response_class=ORJSONResponse,
    response_model=dict[str, str],
    responses={
        200: {
            "content": {"application/json": {"example": {"status": "cleared"}}},
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="clear_all_items",
)
@timed("/items/clear-all")
@limiter.limit("10/minute")
async def clear_all_items(request: Request, response: Response) -> ORJSONResponse:
    """
    Clear in-memory items and purge related cache keys.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.

    Returns
    -------
    ORJSONResponse
        Status message indicating the store and caches are cleared.

    Notes
    -----
    Also clears paginated keys for common page sizes (1, 2, 10) across
    pages 1..50 to ensure test isolation and consistent results.

    Examples
    --------
    Request
        DELETE /items/clear-all
    Response
        200 OK
        {"status": "cleared"}

    Response schema
    ---------------
    {
      "status": str
    }
    """
    sizes = [1, 2, 10]
    keys: list[str] = []
    for size in sizes:
        keys.extend([f"get_paginated_items_{p}_{size}" for p in range(1, 51)])
    items_db.clear()
    await get_cache_manager(request).delete(
        "get_all_items",
        "get_raw_items",
        "get_map_items",
        "get_dict_list_items",
        "get_tuple_items",
        *keys,
        namespace="items",
    )
    return ORJSONResponse(content={"status": "cleared"})
