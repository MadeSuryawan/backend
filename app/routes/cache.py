# app/routes/cache.py
"""FastAPI integration for caching with SlowAPI support."""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse

from app.configs import file_logger
from app.managers import cache_manager
from app.managers.cache_manager import CacheManager
from app.schemas import (
    CacheClearResponse,
    CachePingResponse,
    CacheResetStatsResponse,
    CacheStatsResponse,
    CacheToggleResponse,
)

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/cache", tags=["cache"])


# --- Dependency Injection ---
def get_cache_manager() -> CacheManager:
    """Dependency to get the global cache manager instance."""
    return cache_manager


# Type alias for cleaner signatures
CacheDep = Annotated[CacheManager, Depends(get_cache_manager)]


# --- Routes ---
@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats(manager: CacheDep) -> ORJSONResponse:
    """
    Get cache statistics.

    Returns:
        Cache statistics.
    """
    stats = manager.get_statistics()
    response = CacheStatsResponse(status="success", data=stats)
    return ORJSONResponse(content=response.model_dump())


@router.get("/ping", response_model=CachePingResponse)
async def ping_cache(manager: CacheDep) -> ORJSONResponse:
    """
    Ping cache server.

    Returns:
        Ping result.
    """
    is_alive = await manager.ping()
    if is_alive:
        response = CachePingResponse(status="success", message="Cache server is reachable")
        return ORJSONResponse(content=response.model_dump())

    response = CachePingResponse(
        status="error",
        message="Cache server is not reachable",
        error_code=503,
    )
    return ORJSONResponse(content=response.model_dump(), status_code=503)


@router.get("/reset-stats", response_model=CacheResetStatsResponse)
async def reset_stats(manager: CacheDep) -> ORJSONResponse:
    """
    Reset cache statistics.

    Returns:
        Reset operation result.
    """
    manager.reset_statistics()
    response = CacheResetStatsResponse(status="success", message="Cache statistics reset")
    return ORJSONResponse(content=response.model_dump())


@router.delete("/clear", response_model=CacheClearResponse)
async def clear_cache(manager: CacheDep) -> ORJSONResponse:
    """
    Clear all cache entries.

    Returns:
        Clear operation result.
    """
    await manager.clear()
    response = CacheClearResponse(status="success", message="Cache cleared successfully")
    return ORJSONResponse(content=response.model_dump())


@router.post("/redis/disable", response_model=CacheToggleResponse)
async def disable_redis(manager: CacheDep) -> ORJSONResponse:
    """
    Disable Redis and switch to in-memory cache.

    Returns:
        Toggle operation result with new backend status.
    """
    result = await manager.disable_redis()
    return ORJSONResponse(content=result.model_dump())


@router.post("/redis/enable", response_model=CacheToggleResponse)
async def enable_redis(manager: CacheDep) -> ORJSONResponse:
    """
    Enable Redis and switch from in-memory cache.

    Returns:
        Toggle operation result with new backend status.
    """
    result = await manager.enable_redis()
    return ORJSONResponse(content=result.model_dump())
