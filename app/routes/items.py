from logging import getLogger

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import ORJSONResponse
from starlette.status import HTTP_404_NOT_FOUND

from app.configs import file_logger
from app.decorators import cache_busting, timed
from app.decorators.caching import cached
from app.managers import cache_manager, limiter
from app.schemas import Item, ItemUpdate

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/items", tags=["items"])


# In-memory database (for demo purposes)
items_db: dict[int, Item] = {}


# --- Routes ---
@router.post(
    "/",
    response_model=Item,
    summary="Create new item",
    response_class=ORJSONResponse,
)
@timed("/items/create")
@limiter.limit("2/minute")
@cache_busting(cache_manager, keys=["get_all_items"], namespace="items")
async def create_item(item: Item, request: Request, response: Response) -> Item:
    """
    Create new item with cache busting.

    Rate limited to 2 requests per minute.
    Invalidates the items list cache.
    """
    logger.info(f"Creating item: {item.name}")
    items_db[item.id] = item
    return item


@router.get(
    "/get-item/{item_id}",
    summary="Get specific item",
    response_class=ORJSONResponse,
    response_model=Item,
)
@timed("/items/get")
@limiter.limit("10/minute")
@cached(
    cache_manager,
    ttl=5,
    namespace="items",
    key_builder=lambda item_id, **kw: f"item_{item_id}",
    response_model=Item,
)
async def get_item(item_id: int, request: Request, response: Response) -> Item:
    """
    Get specific item with caching.

    Rate limited to 200 requests per minute.
    Results cached for 1 hour.
    """
    logger.info(f"Fetching item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Item not found")
    return items_db[item_id]


@router.get(
    "/all-items",
    summary="Get all items",
    response_class=ORJSONResponse,
    response_model=dict[str, list[Item]],
)
@timed("/items/all")
@limiter.limit("10/minute")
@cached(cache_manager, ttl=3600, namespace="items", key_builder=lambda **kw: "get_all_items")
async def get_all_items(request: Request, response: Response) -> ORJSONResponse:
    """
    Get all items with caching.

    Rate limited to 100 requests per minute.
    Results cached for 1 hour.
    """
    logger.info("Fetching all items")
    return ORJSONResponse(content={"items": list(items_db.values())})


@router.put(
    "/update-item/{item_id}",
    summary="Update specific item",
    response_class=ORJSONResponse,
    response_model=Item,
)
@timed("/items/update")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "get_all_items"],
    namespace="items",
)
async def update_item(
    item_id: int,
    item_update: ItemUpdate,
    request: Request,
    response: Response,
) -> Item:
    """
    Update item with cache busting.

    Rate limited to 50 requests per minute.
    Invalidates specific item and items list cache.
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
    summary="Delete specific item",
    response_class=ORJSONResponse,
    response_model=dict[str, str],
)
@timed("/items/delete")
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "get_all_items"],
    namespace="items",
)
async def delete_item(item_id: int, request: Request, response: Response) -> ORJSONResponse:
    """
    Delete item with cache busting.

    Rate limited to 50 requests per minute.
    Invalidates specific item and items list cache.
    """
    logger.info(f"Deleting item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    del items_db[item_id]
    return ORJSONResponse(content={"message": "Item deleted successfully"})
