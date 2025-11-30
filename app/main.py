# app/main.py
"""BaliBlissed Backend - Seamless caching integration with Redis for FastAPI."""

from logging import getLogger

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import ORJSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.status import HTTP_404_NOT_FOUND

from app.configs import file_logger
from app.decorators import cache_busting, cached
from app.errors import (
    CacheExceptionError,
    EmailServiceError,
    cache_exception_handler,
    email_service_exception_handler,
)
from app.managers import cache_manager, limiter, rate_limit_exceeded_handler
from app.middleware import (
    add_compression,
    add_request_logging,
    add_security_headers,
    configure_cors,
    lifespan,
)
from app.routes import cache_router, email_router
from app.schemas import Item, ItemUpdate

app = FastAPI(
    title="BaliBlissed Backend",
    description="Seamless caching integration with Redis for FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

add_security_headers(app)
add_request_logging(app)
configure_cors(app)
add_compression(app)

app.include_router(cache_router)
app.include_router(email_router)

app.add_exception_handler(
    CacheExceptionError,
    cache_exception_handler,
)


app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_exceeded_handler,
)

app.add_exception_handler(
    EmailServiceError,
    email_service_exception_handler,
)


logger = file_logger(getLogger(__name__))

# In-memory database (for demo purposes)
items_db: dict[int, Item] = {}


# Routes
@app.get("/", tags=["health"])
@limiter.exempt
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Welcome to FastAPI Redis Cache"}


@app.post("/create-item", tags=["items"])
@limiter.limit("2/minute")
@cache_busting(cache_manager, keys=["get_all_items"], namespace="items")
async def create_item(item: Item, request: Request, response: Response) -> Item:
    """
    Create new item with cache busting.

    Rate limited to 50 requests per minute.
    Invalidates the items list cache.
    """
    logger.info(f"Creating item: {item.name}")
    items_db[item.id] = item
    return item


@app.get("/get-item/{item_id}", tags=["items"])
@limiter.limit("10/minute")
@cached(
    cache_manager,
    ttl=5,
    namespace="items",
    key_builder=lambda item_id, **kw: f"item_{item_id}",
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


@app.get(
    "/all-items",
    tags=["items"],
    response_class=ORJSONResponse,
    response_model=dict[str, list[Item]],
)
@limiter.limit("10/minute")
@cached(cache_manager, ttl=3600, namespace="items", key_builder=lambda **kw: "get_all_items")
async def get_all_items(request: Request, response: Response) -> dict[str, list[Item]]:
    """
    Get all items with caching.

    Rate limited to 100 requests per minute.
    Results cached for 1 hour.
    """
    logger.info("Fetching all items")
    return {"items": list(items_db.values())}


@app.put("/update-item/{item_id}", tags=["items"])
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


@app.delete("/delete-item/{item_id}", tags=["items"])
@limiter.limit("10/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "get_all_items"],
    namespace="items",
)
async def delete_item(item_id: int, request: Request, response: Response) -> dict[str, str]:
    """
    Delete item with cache busting.

    Rate limited to 50 requests per minute.
    Invalidates specific item and items list cache.
    """
    logger.info(f"Deleting item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    del items_db[item_id]
    return {"message": "Item deleted successfully"}


# Health check
@app.get("/health", tags=["health"])
@limiter.exempt
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    try:
        is_alive = await cache_manager.ping()
        status = "healthy" if is_alive else "unhealthy"
    except Exception:
        logger.exception("Health check failed")
        return {"status": "unhealthy", "cache": "error"}

    return {"status": status, "cache": "connected" if is_alive else "disconnected"}


if __name__ == "__main__":
    from uvicorn import run

    run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        reload=True,
        loop="uvloop",
        http="httptools",
    )
