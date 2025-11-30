from typing import Any

from pydantic import BaseModel, ConfigDict


class CacheStatsResponse(BaseModel):
    """Cache statistics response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    status: str
    data: dict[str, Any]


class CacheClearResponse(BaseModel):
    """Cache clear response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    status: str
    message: str
    error_code: int | None = None


class CachePingResponse(BaseModel):
    """Cache ping response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    status: str
    message: str
    error_code: int | None = None


class CacheResetStatsResponse(BaseModel):
    """Cache reset statistics response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    status: str
    message: str
    error_code: int | None = None
