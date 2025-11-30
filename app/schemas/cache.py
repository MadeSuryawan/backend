from typing import Any

from pydantic import BaseModel


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
