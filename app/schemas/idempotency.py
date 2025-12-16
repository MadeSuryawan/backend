"""Idempotency-related schemas."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IdempotencyStatus(str, Enum):
    """Status of an idempotency record."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class IdempotencyRecord(BaseModel):
    """Schema for idempotency record stored in Redis."""

    status: IdempotencyStatus
    response: Any | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    model_config = {"use_enum_values": True}


class IdempotencyKeyResponse(BaseModel):
    """Response schema for idempotency key operations."""

    key: str
    namespace: str
    status: str
    message: str


class IdempotencyMetrics(BaseModel):
    """Metrics for idempotency operations."""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    duplicate_requests_blocked: int = 0
    failed_requests: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as percentage."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100


class IdempotencyAdminRequest(BaseModel):
    """Request schema for admin idempotency operations."""

    namespace: str = Field(..., description="Idempotency namespace (e.g., 'auth:register')")
    idempotency_key: str = Field(..., description="The idempotency key (UUID)")


class IdempotencyAdminResponse(BaseModel):
    """Response schema for admin idempotency operations."""

    success: bool
    message: str
    namespace: str | None = None
    key: str | None = None
