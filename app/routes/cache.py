# app/routes/cache.py
"""FastAPI integration for caching with SlowAPI support."""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse

from app.configs import file_logger
from app.decorators import timed
from app.managers import cache_manager, limiter
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
@router.get(
    "/stats",
    response_model=CacheStatsResponse,
    summary="Get cache statistics",
    response_class=ORJSONResponse,
)
@timed("/cache/stats")
@limiter.limit("10/minute")
async def get_cache_stats(request: Request, manager: CacheDep) -> ORJSONResponse:
    """
    Get cache statistics.

    Returns:
        Cache statistics.
    """
    stats = manager.get_statistics()
    response = CacheStatsResponse(status="success", data=stats)
    return ORJSONResponse(content=response.model_dump())


@router.get(
    "/ping",
    response_model=CachePingResponse,
    summary="Ping cache server",
    response_class=ORJSONResponse,
)
@timed("/cache/ping")
@limiter.limit("20/minute")
async def ping_cache(request: Request, manager: CacheDep) -> ORJSONResponse:
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


@router.get(
    "/reset-stats",
    response_model=CacheResetStatsResponse,
    summary="Reset cache statistics",
    response_class=ORJSONResponse,
)
@timed("/cache/reset-stats")
@limiter.limit("5/hour")
async def reset_stats(request: Request, manager: CacheDep) -> ORJSONResponse:
    """
    Reset cache statistics.

    Returns:
        Reset operation result.
    """
    manager.reset_statistics()
    response = CacheResetStatsResponse(status="success", message="Cache statistics reset")
    return ORJSONResponse(content=response.model_dump())


@router.delete(
    "/clear",
    response_model=CacheClearResponse,
    summary="Clear all cache entries",
    response_class=ORJSONResponse,
)
@timed("/cache/clear")
@limiter.limit("2/hour")
async def clear_cache(request: Request, manager: CacheDep) -> ORJSONResponse:
    """
    Clear all cache entries.

    Returns:
        Clear operation result.
    """
    await manager.clear()
    response = CacheClearResponse(status="success", message="Cache cleared successfully")
    return ORJSONResponse(content=response.model_dump())


@router.post(
    "/redis/disable",
    response_model=CacheToggleResponse,
    summary="Disable Redis and switch to in-memory cache",
    response_class=ORJSONResponse,
)
@timed("/cache/redis/disable")
@limiter.limit("1/hour")
async def disable_redis(request: Request, manager: CacheDep) -> ORJSONResponse:
    """
    Disable Redis and switch to in-memory cache.

    Returns:
        Toggle operation result with new backend status.
    """
    result = await manager.disable_redis()
    return ORJSONResponse(content=result.model_dump())


@router.post(
    "/redis/enable",
    response_model=CacheToggleResponse,
    summary="Enable Redis and switch from in-memory cache",
    response_class=ORJSONResponse,
)
@timed("/cache/redis/enable")
@limiter.limit("1/hour")
async def enable_redis(request: Request, manager: CacheDep) -> ORJSONResponse:
    """
    Enable Redis and switch from in-memory cache.

    Returns:
        Toggle operation result with new backend status.
    """
    result = await manager.enable_redis()
    return ORJSONResponse(content=result.model_dump())
