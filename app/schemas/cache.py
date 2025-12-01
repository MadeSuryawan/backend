from typing import Any

from pydantic import BaseModel, ConfigDict


class CacheStatistics(BaseModel):
    """Cache statistics model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    hits: int
    misses: int
    sets: int
    deletes: int
    evictions: int
    errors: int
    total_bytes_written: int
    total_bytes_read: int
    hit_rate: str
    total_requests: int
    created_at: str
    last_updated_at: str


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    backend: str
    statistics: CacheStatistics
    status: str
    # Redis-specific fields (optional)
    latency_ms: float | None = None
    connected_clients: int | None = None
    used_memory_human: str | None = None
    uptime_seconds: int | None = None
    redis_version: str | None = None
    # In-memory-specific fields (optional)
    info: dict[str, Any] | None = None
    # Error field (optional)
    error: str | None = None


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


class CacheToggleResponse(BaseModel):
    """Cache toggle (enable/disable Redis) response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    status: str
    message: str
    backend: str
    error_code: int | None = None
