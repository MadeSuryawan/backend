"""FastAPI integration for caching with SlowAPI support."""

from logging import getLogger
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.errors import CacheExceptionError
from app.managers import cache_manager
from app.utils import file_logger

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/cache", tags=["cache"])


class CacheStatsResponse(BaseModel):
    """Cache statistics response model."""

    status: str
    data: dict[str, Any]


class CacheClearResponse(BaseModel):
    """Cache clear response model."""

    status: str
    message: str
    error_code: int | None = None


class CachePingResponse(BaseModel):
    """Cache ping response model."""

    status: str
    message: str
    error_code: int | None = None


class CacheResetStatsResponse(BaseModel):
    """Cache reset statistics response model."""

    status: str
    message: str
    error_code: int | None = None


@router.get("/stats", response_model=CacheStatsResponse, tags=["cache"])
async def get_cache_stats() -> CacheStatsResponse:
    """
    Get cache statistics.

    Returns:
        Cache statistics.
    """
    try:
        stats = cache_manager.get_statistics()
        return CacheStatsResponse(status="success", data=stats)
    except Exception as e:
        logger.exception("Failed to get cache stats")
        return CacheStatsResponse(status="error", data={"message": str(e)})


@router.get("/ping", response_model=CachePingResponse, tags=["cache"])
async def ping_cache() -> CachePingResponse:
    """
    Ping cache server.

    Returns:
        Ping result.
    """
    try:
        is_alive = await cache_manager.ping()
        if is_alive:
            return CachePingResponse(status="success", message="Cache server is reachable")
        return CachePingResponse(
            status="error",
            message="Cache server is not reachable",
            error_code=503,
        )
    except Exception as e:
        logger.exception("Cache ping failed")
        return CachePingResponse(status="error", message=str(e), error_code=503)


@router.get("/reset-stats", tags=["cache"])
async def reset_stats() -> CacheResetStatsResponse:
    """
    Reset cache statistics.

    Returns:
        Reset operation result.
    """
    try:
        cache_manager.reset_statistics()
    except Exception as e:
        logger.exception("Failed to reset cache stats")
        return CacheResetStatsResponse(status="error", message=str(e), error_code=500)
    return CacheResetStatsResponse(status="success", message="Cache statistics reset")


@router.delete("/clear", response_model=CacheClearResponse, tags=["cache"])
async def clear_cache() -> CacheClearResponse:
    """
    Clear all cache entries.

    Returns:
        Clear operation result.
    """
    try:
        await cache_manager.clear()
        return CacheClearResponse(status="success", message="Cache cleared successfully")
    except Exception as e:
        logger.exception("Failed to clear cache")
        return CacheClearResponse(status="error", message=str(e), error_code=500)


def create_cache_error_handler(app: FastAPI) -> None:
    """
    Add cache exception error handlers to FastAPI application.

    Args:
        app: FastAPI application.
    """

    @app.exception_handler(CacheExceptionError)
    async def cache_exception_handler(request: Request, exc: CacheExceptionError) -> JSONResponse:
        """
        Handle cache exceptions.

        Args:
            request: Request object.
            exc: Cache exception.

        Returns:
            Error response.
        """
        logger.exception(f"Cache exception occurred: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Cache operation failed",
                "error": str(exc),
            },
        )
