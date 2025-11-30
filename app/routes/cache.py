"""FastAPI integration for caching with SlowAPI support."""

from logging import getLogger

from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

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


@router.get("/stats", response_model=CacheStatsResponse)
async def get_cache_stats() -> ORJSONResponse:
    """
    Get cache statistics.

    Returns:
        Cache statistics.
    """
    stats = cache_manager.get_statistics()
    response = CacheStatsResponse(status="success", data=stats)
    return ORJSONResponse(content=response.model_dump())


@router.get("/ping", response_model=CachePingResponse)
async def ping_cache() -> ORJSONResponse:
    """
    Ping cache server.

    Returns:
        Ping result.
    """
    is_alive = await cache_manager.ping()
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
async def reset_stats() -> ORJSONResponse:
    """
    Reset cache statistics.

    Returns:
        Reset operation result.
    """
    cache_manager.reset_statistics()
    response = CacheResetStatsResponse(status="success", message="Cache statistics reset")
    return ORJSONResponse(content=response.model_dump())


@router.delete("/clear", response_model=CacheClearResponse)
async def clear_cache() -> ORJSONResponse:
    """
    Clear all cache entries.

    Returns:
        Clear operation result.
    """
    await cache_manager.clear()
    response = CacheClearResponse(status="success", message="Cache cleared successfully")
    return ORJSONResponse(content=response.model_dump())
