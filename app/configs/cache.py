"""
Cache configuration module.

This module provides cache configuration settings for the application.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheConfig(BaseSettings):
    """Cache configuration."""

    model_config = SettingsConfigDict(env_prefix="CACHE_", case_sensitive=False)

    default_ttl: int = 3600  # 1 hour
    max_ttl: int = 86400  # 24 hours
    key_prefix: str = "cache"
    compression_enabled: bool = True
    compression_threshold: int = 1024  # bytes
    strategy: Literal["LRU", "FIFO"] = "LRU"
    enable_statistics: bool = True
    cleanup_interval: int = 300  # 5 minutes
