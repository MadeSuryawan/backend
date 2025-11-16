"""Configuration module for Redis caching settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisCacheConfig(BaseSettings):
    """Redis cache configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    ssl: bool = False
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    health_check_interval: int = 30
    max_connections: int = 50
    decode_responses: bool = True
    encoding: str = "utf-8"


class CacheConfig(BaseSettings):
    """Cache configuration."""

    model_config = SettingsConfigDict(env_prefix="CACHE_", case_sensitive=False)

    default_ttl: int = 3600  # 1 hour
    max_ttl: int = 86400  # 24 hours
    key_prefix: str = "cache:"
    compression_enabled: bool = False
    compression_threshold: int = 1024  # bytes
    strategy: Literal["LRU", "FIFO"] = "LRU"
    enable_statistics: bool = True
    cleanup_interval: int = 300  # 5 minutes


class ApplicationConfig(BaseSettings):
    """Application configuration."""

    model_config = SettingsConfigDict(case_sensitive=False)

    app_name: str = "FastAPI Redis Cache"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"
    redis: RedisCacheConfig = RedisCacheConfig()
    cache: CacheConfig = CacheConfig()
