from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DateTimeResponse(BaseModel):
    """
    Standard datetime representation in API responses.

    Provides multiple formats for datetime display:
    - utc: ISO 8601 format in UTC
    - local: User's local time with timezone abbreviation
    - human: Human-friendly relative time (e.g., "2 hours ago")
    - timezone: The timezone used for local conversion

    Examples:
        >>> dt_response = DateTimeResponse(
        ...     utc="2026-02-13T15:00:00Z",
        ...     local="2026-02-13 10:00:00 EST",
        ...     human="5 hours ago",
        ...     timezone="America/New_York"
        ... )

    """

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    utc: str = Field(
        ...,
        description="ISO 8601 UTC timestamp (e.g., '2026-02-13T15:00:00Z')",
    )
    local: str = Field(
        ...,
        description="User's local time with timezone abbreviation (e.g., '2026-02-13 10:00:00 EST')",
    )
    human: str = Field(
        ...,
        description="Human-friendly relative time (e.g., '2 hours ago', 'Yesterday')",
    )
    timezone: str = Field(
        ...,
        description="Timezone used for local conversion (e.g., 'America/New_York')",
    )


class CacheStatisticsData(BaseModel):
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


class CircuitBreakerStatus(BaseModel):
    """Circuit breaker status model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    name: str
    state: str
    failure_count: int
    failure_threshold: int
    last_failure_time: float | None
    time_until_reset: float
    success_threshold: int
    half_open_successes: int


class ServicesStatus(BaseModel):
    """Services status model for health check."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    ai_client: str = Field(description="AI client initialization status")
    email_client: str = Field(description="Email client initialization status")
    ai_circuit_breaker: CircuitBreakerStatus
    email_circuit_breaker: CircuitBreakerStatus


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    version: str = Field(description="API version")
    status: str = Field(description="Overall health status")
    timestamp: str = Field(description="Current timestamp")
    services: ServicesStatus = Field(description="Status of dependent services")
    cache: "CacheHealthResponse | None" = Field(
        default=None,
        description="Cache health information",
    )


class CacheHealthResponse(BaseModel):
    """Cache health response model (nested in HealthCheckResponse)."""

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    backend: str
    statistics: CacheStatisticsData
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
    data: CacheStatisticsData


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
