# app/main.py
"""FastAPI Redis Cache - Seamless caching integration with Redis for FastAPI."""

from logging import getLogger

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.decorators.caching import cache_busting, cached
from app.managers.cache_manager import cache_manager
from app.middleware.middleware import (
    add_compression,
    add_request_logging,
    add_security_headers,
    configure_cors,
    lifespan,
)
from app.routes.cache import router as cache_router
from app.utils.helpers import file_logger

# Configure logging
logger = file_logger(getLogger(__name__))

# FastAPI app
app = FastAPI(
    title="FastAPI Redis Cache",
    description="Seamless caching integration with Redis for FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware
add_security_headers(app)
add_request_logging(app)
configure_cors(app)
add_compression(app)

# Add cache management routes
app.include_router(cache_router)

# SlowAPI rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


# Pydantic models
class Item(BaseModel):
    """Item model."""

    id: int
    name: str
    description: str | None = None
    price: float


class ItemUpdate(BaseModel):
    """Item update model."""

    name: str | None = None
    description: str | None = None
    price: float | None = None


# In-memory database (for demo purposes)
items_db: dict[int, Item] = {}


# Routes
@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Welcome to FastAPI Redis Cache"}


@app.post("/create-item", tags=["items"])
@limiter.limit("50/minute")
@cache_busting(cache_manager, keys=["get_all_items"], namespace="items")
async def create_item(item: Item, request: Request) -> Item:
    """Create new item with cache busting.

    Rate limited to 50 requests per minute.
    Invalidates the items list cache.
    """
    logger.info(f"Creating item: {item.name}")
    items_db[item.id] = item
    return item


@app.get("/get-item/{item_id}", tags=["items"])
@limiter.limit("200/minute")
@cached(
    cache_manager,
    ttl=300,
    namespace="items",
    key_builder=lambda item_id, **kw: f"item_{item_id}",
)
async def get_item(item_id: int, request: Request) -> Item:
    """Get specific item with caching.

    Rate limited to 200 requests per minute.
    Results cached for 5 minutes.
    """
    logger.info(f"Fetching item {item_id}")
    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")
    return items_db[item_id]


@app.get("/all-items", tags=["items"])
@limiter.limit("100/minute")
@cached(cache_manager, ttl=600, namespace="items")
async def get_all_items(request: Request) -> dict[str, list[Item]]:
    """Get all items with caching.

    Rate limited to 100 requests per minute.
    Results cached for 10 minutes.
    """
    logger.info("Fetching all items")
    return {"items": list(items_db.values())}


@app.put("/update-item/{item_id}", tags=["items"])
@limiter.limit("50/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "get_all_items"],
    namespace="items",
)
async def update_item(item_id: int, item_update: ItemUpdate, request: Request) -> Item:
    """Update item with cache busting.

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
@limiter.limit("50/minute")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "get_all_items"],
    namespace="items",
)
async def delete_item(item_id: int, request: Request) -> dict[str, str]:
    """Delete item with cache busting.

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
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info", reload=True)
