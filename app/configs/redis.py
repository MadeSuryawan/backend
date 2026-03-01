"""
Redis configuration module.

This module provides Redis cache configuration with SSL/TLS and authentication support,
along with connection pool kwargs for Redis client initialization.
"""

from ssl import CERT_NONE, CERT_OPTIONAL, CERT_REQUIRED
from typing import Any
from warnings import warn

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.configs.settings import settings


class RedisConfig(BaseSettings):
    """Redis cache configuration with SSL/TLS and authentication support."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    # Basic connection settings
    host: str = settings.REDIS_HOST
    port: int = settings.REDIS_PORT
    db: int = settings.REDIS_DB
    password: str | None = settings.REDIS_PASSWORD
    username: str | None = None  # Redis ACL username (Redis 6+)
    url: str | None = settings.REDIS_URL

    # SSL/TLS Settings
    ssl: bool = False
    ssl_ca_certs: str | None = None  # Path to CA certificates file
    ssl_ca_path: str | None = None  # Path to CA certificates directory (combined into ssl_ca_certs)
    ssl_cert_reqs: str = "required"  # none, optional, required
    ssl_certfile: str | None = None  # Path to client certificate
    ssl_keyfile: str | None = None  # Path to client private key
    ssl_check_hostname: bool = True  # Verify hostname matches certificate

    # Connection pool settings
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    socket_keepalive: bool = True
    health_check_interval: int = 30
    max_connections: int = 50
    decode_responses: bool = True
    encoding: str = "utf-8"

    @property
    def ssl_cert_reqs_value(self) -> int:
        """Get SSLContext verify mode from string setting."""
        mapping = {
            "none": CERT_NONE,
            "optional": CERT_OPTIONAL,
            "required": CERT_REQUIRED,
        }
        return mapping.get(self.ssl_cert_reqs.lower(), CERT_REQUIRED)


# Create global Redis config instance
redis_config = RedisConfig()

# Build redis connection pool kwargs dynamically
pool_kwargs: dict[str, Any] = {
    "host": redis_config.host,
    "port": redis_config.port,
    "db": redis_config.db,
    "password": redis_config.password,
    "username": redis_config.username,
    "socket_timeout": redis_config.socket_timeout,
    "socket_connect_timeout": redis_config.socket_connect_timeout,
    "socket_keepalive": redis_config.socket_keepalive,
    "max_connections": redis_config.max_connections,
    "decode_responses": redis_config.decode_responses,
    "encoding": redis_config.encoding,
    "health_check_interval": redis_config.health_check_interval,
}

if redis_config.url:
    # If a full URL/socket path is provided, we might need to parse it or use from_url
    # For now, let's just make sure redis-py can handle it.
    # However, pool_kwargs is passed to ConnectionPool(**pool_kwargs).
    # ConnectionPool doesn't accept 'url'.
    # We need to handle Unix socket specifically if it's in the URL or implied.
    is_unix = redis_config.url.startswith("unix://")
    is_redis_unix = redis_config.url.startswith("redis+unix://")

    if is_unix or is_redis_unix:
        pool_kwargs["connection_class"] = __import__(
            "redis.asyncio",
        ).asyncio.UnixDomainSocketConnection

        # Extract path
        if is_unix:
            pool_kwargs["path"] = redis_config.url.replace("unix://", "")
        else:
            pool_kwargs["path"] = redis_config.url.replace("redis+unix://", "")

        # Remove TCP specific args
        pool_kwargs.pop("host", None)
        pool_kwargs.pop("port", None)
        pool_kwargs.pop(
            "socket_keepalive",
            None,
        )  # Unix sockets don't support keepalive the same way

if redis_config.socket_keepalive and "socket_keepalive" in pool_kwargs:
    pool_kwargs["socket_keepalive_options"] = {}

# Configure SSL/TLS settings
if redis_config.ssl:
    pool_kwargs["ssl"] = True
    pool_kwargs["ssl_cert_reqs"] = redis_config.ssl_cert_reqs_value
    pool_kwargs["ssl_check_hostname"] = redis_config.ssl_check_hostname

    # CA certificates (file takes precedence over path)
    if redis_config.ssl_ca_certs:
        pool_kwargs["ssl_ca_certs"] = redis_config.ssl_ca_certs
    elif redis_config.ssl_ca_path:
        # Note: redis-py doesn't support ssl_ca_path directly
        # Users should combine certificates into a single bundle file
        warn(
            "ssl_ca_path is set but redis-py requires a single CA bundle file. "
            "Please use ssl_ca_certs instead, or combine certificates into a bundle.",
            stacklevel=2,
        )

    # Client certificate authentication
    if redis_config.ssl_certfile:
        pool_kwargs["ssl_certfile"] = redis_config.ssl_certfile
    if redis_config.ssl_keyfile:
        pool_kwargs["ssl_keyfile"] = redis_config.ssl_keyfile
