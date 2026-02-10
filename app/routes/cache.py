# app/routes/cache.py
"""
Cache Routes.

FastAPI integration for caching with SlowAPI support: statistics, ping, reset,
clear, and backend toggles.

Rate Limiting
-------------
All endpoints include explicit rate limits and `429` responses.
"""

from logging import getLogger

from fastapi import APIRouter, Request
from fastapi.responses import ORJSONResponse

from app.decorators.metrics import timed
from app.dependencies import AdminUserDep, CacheDep
from app.managers.rate_limiter import limiter
from app.schemas import (
    CacheClearResponse,
    CachePingResponse,
    CacheResetStatsResponse,
    CacheStatsResponse,
    CacheToggleResponse,
)
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/cache", tags=["🧰 Cache"])


# --- Routes ---
@router.get(
    "/stats",
    response_model=CacheStatsResponse,
    summary="Get cache statistics",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "data": {"hits": 10, "misses": 2}},
                },
            },
        },
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
    operation_id="cache_stats",
)
@timed("/cache/stats")
@limiter.limit("10/minute")
async def get_cache_stats(
    request: Request,
    manager: CacheDep,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Get cache statistics.

    Parameters
    ----------
    request : Request
        Current request context.
    manager : CacheManager
        Cache manager dependency.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Cache statistics payload.

    Notes
    -----
    Rate limited to 10 requests per minute.
    """
    stats = manager.get_statistics()
    response = CacheStatsResponse(status="success", data=stats)
    return ORJSONResponse(content=response.model_dump())


@router.get(
    "/ping",
    response_model=CachePingResponse,
    summary="Ping cache server",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Cache server is reachable"},
                },
            },
        },
        503: {
            "description": "Cache server is not reachable",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "message": "Cache server is not reachable",
                        "error_code": 503,
                    },
                },
            },
        },
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
    operation_id="cache_ping",
)
@timed("/cache/ping")
@limiter.limit("20/minute")
async def ping_cache(
    request: Request,
    manager: CacheDep,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Ping cache server.

    Parameters
    ----------
    request : Request
        Current request context.
    manager : CacheManager
        Cache manager dependency.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Ping result payload; 503 when unreachable.

    Notes
    -----
    Rate limited to 20 requests per minute.
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
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Cache statistics reset"},
                },
            },
        },
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
    operation_id="cache_reset_stats",
)
@timed("/cache/reset-stats")
@limiter.limit("5/hour")
async def reset_stats(
    request: Request,
    manager: CacheDep,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Reset cache statistics.

    Parameters
    ----------
    request : Request
        Current request context.
    manager : CacheManager
        Cache manager dependency.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Reset operation result payload.

    Notes
    -----
    Rate limited to 5 requests per hour.
    """
    manager.reset_statistics()
    response = CacheResetStatsResponse(status="success", message="Cache statistics reset")
    return ORJSONResponse(content=response.model_dump())


@router.delete(
    "/clear",
    response_model=CacheClearResponse,
    summary="Clear all cache entries",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Cache cleared successfully"},
                },
            },
        },
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
    operation_id="cache_clear",
)
@timed("/cache/clear")
@limiter.limit("2/hour")
async def clear_cache(
    request: Request,
    manager: CacheDep,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Clear all cache entries.

    Parameters
    ----------
    request : Request
        Current request context.
    manager : CacheManager
        Cache manager dependency.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Clear operation result payload.

    Notes
    -----
    Rate limited to 2 requests per hour.
    """
    await manager.clear()
    response = CacheClearResponse(status="success", message="Cache cleared successfully")
    return ORJSONResponse(content=response.model_dump())


@router.post(
    "/redis/disable",
    response_model=CacheToggleResponse,
    summary="Disable Redis and switch to in-memory cache",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Switched to in-memory cache"},
                },
            },
        },
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
    operation_id="cache_redis_disable",
)
@timed("/cache/redis/disable")
@limiter.limit("1/hour")
async def disable_redis(
    request: Request,
    manager: CacheDep,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Disable Redis and switch to in-memory cache.

    Parameters
    ----------
    request : Request
        Current request context.
    manager : CacheManager
        Cache manager dependency.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Toggle operation result with new backend status.

    Notes
    -----
    Rate limited to 1 request per hour.
    """
    result = await manager.disable_redis()
    return ORJSONResponse(content=result.model_dump())


@router.post(
    "/redis/enable",
    response_model=CacheToggleResponse,
    summary="Enable Redis and switch from in-memory cache",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Redis enabled"},
                },
            },
        },
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
    operation_id="cache_redis_enable",
)
@timed("/cache/redis/enable")
@limiter.limit("1/hour")
async def enable_redis(
    request: Request,
    manager: CacheDep,
    admin_user: AdminUserDep,
) -> ORJSONResponse:
    """
    Enable Redis and switch from in-memory cache.

    Parameters
    ----------
    request : Request
        Current request context.
    manager : CacheManager
        Cache manager dependency.
    admin_user : UserDB
        Admin user (enforced by AdminUserDep dependency).

    Returns
    -------
    ORJSONResponse
        Toggle operation result with new backend status.

    Notes
    -----
    Rate limited to 1 request per hour.
    """
    result = await manager.enable_redis()
    return ORJSONResponse(content=result.model_dump())
