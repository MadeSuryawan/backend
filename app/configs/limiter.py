"""
Rate limiter configuration module.

This module provides rate limiting configuration for the application.
"""

from pydantic import BaseModel, ConfigDict

from app.configs.settings import settings

RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 3600


class LimiterConfig(BaseModel):
    """Configuration for rate limiting."""

    default_limits: list[str] = [f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW}s"]
    storage_uri: str = settings.redis_url
    in_memory_fallback_enabled: bool = settings.IN_MEMORY_FALLBACK_ENABLED
    headers_enabled: bool = settings.HEADERS_ENABLED

    model_config = ConfigDict(from_attributes=True)
