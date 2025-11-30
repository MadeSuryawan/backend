"""FastAPI integration for caching with SlowAPI support."""

from logging import getLogger

from fastapi import APIRouter

from app.configs import file_logger
from app.managers import cache_manager
from app.schemas import (
    CacheClearResponse,
    CachePingResponse,
    CacheResetStatsResponse,
    CacheStatsResponse,
)

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats", response_model=CacheStatsResponse, tags=["cache"])
async def get_cache_stats() -> CacheStatsResponse:
    """
    Get cache statistics.

    Returns:
        Cache statistics.
    """
    stats = cache_manager.get_statistics()
    return CacheStatsResponse(status="success", data=stats)


@router.get("/ping", response_model=CachePingResponse, tags=["cache"])
async def ping_cache() -> CachePingResponse:
    """
    Ping cache server.

    Returns:
        Ping result.
    """
    is_alive = await cache_manager.ping()
    if is_alive:
        return CachePingResponse(status="success", message="Cache server is reachable")
    return CachePingResponse(
        status="error",
        message="Cache server is not reachable",
        error_code=503,
    )


@router.get("/reset-stats", tags=["cache"])
async def reset_stats() -> CacheResetStatsResponse:
    """
    Reset cache statistics.

    Returns:
        Reset operation result.
    """
    cache_manager.reset_statistics()
    return CacheResetStatsResponse(status="success", message="Cache statistics reset")


@router.delete("/clear", response_model=CacheClearResponse, tags=["cache"])
async def clear_cache() -> CacheClearResponse:
    """
    Clear all cache entries.

    Returns:
        Clear operation result.
    """
    await cache_manager.clear()
    return CacheClearResponse(status="success", message="Cache cleared successfully")
