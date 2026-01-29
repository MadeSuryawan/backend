"""
Application settings and configuration constants.

This module contains application settings, constants, and configuration
values for the BaliBlissed backend application.
"""

from pathlib import Path
from typing import Any, Literal

from google.genai.types import (
    GenerateContentConfig,
    GoogleSearch,
    HarmBlockThreshold,
    HarmCategory,
    SafetySetting,
    Tool,
)
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich import print as rprint

ENV_FILE = Path().cwd() / "secrets" / ".env"

# --- Constants ---
MAX_QUERY_LENGTH = 1000
MAX_MESSAGE_LENGTH = 2000
MAX_DESTINATION_LENGTH = 100
MAX_NAME_LENGTH = 100
MIN_TRIP_DURATION = 1
MAX_TRIP_DURATION = 30
MAX_INTERESTS_COUNT = 4
MIN_MESSAGE_LENGTH = 10

WHATSAPP_NUMBER = "+6285847006743"

# Rate limiting constants
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# AI Model Configuration
GEMINI_MODEL = "gemini-2.0-flash"

Harm = HarmCategory
Block = HarmBlockThreshold

# Safety settings for content generation
SAFETY_SETTINGS = [
    SafetySetting(
        category=Harm.HARM_CATEGORY_HARASSMENT,
        threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=Harm.HARM_CATEGORY_HATE_SPEECH,
        threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=Harm.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
    ),
    SafetySetting(
        category=Harm.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
    ),
]

# Tools: Explicitly enable only what needed (Google Search)
SEARCH_TOOL = [Tool(google_search=GoogleSearch())]

GENERATION_CONFIG = GenerateContentConfig(
    temperature=0.7,
    top_p=0.8,
    top_k=40,
    max_output_tokens=8192,  # 4096 * 2
    # response_mime_type="application/json",
    # system_instruction="You are a friendly customer service assistant for a Bali travel agency called BaliBlissed.",
    safety_settings=SAFETY_SETTINGS,
    tools=SEARCH_TOOL,
)


class SecurityInfo(BaseModel):
    description: str
    memory_cost: int
    time_cost: int
    parallelism: int
    hash_time: str


CONFIG_MAP: dict[str, SecurityInfo] = {
    "development": SecurityInfo(
        description="Fast hashing for development/testing",
        memory_cost=65536,  # 64 MB
        time_cost=1,  # 1 iteration
        parallelism=1,  # 1 thread
        hash_time="~20ms",
    ),
    "standard": SecurityInfo(
        description="Balanced security and performance (default)",
        memory_cost=524288,  # 512 MB
        time_cost=2,  # 2 iterations
        parallelism=2,  # 2 threads
        hash_time="~100-150ms",
    ),
    "high": SecurityInfo(
        description="High security, slower hashing",
        memory_cost=1048576,  # 1 GB
        time_cost=3,  # 3 iterations
        parallelism=4,  # 4 threads
        hash_time="~500ms",
    ),
    "paranoid": SecurityInfo(
        description="Maximum security, very slow",
        memory_cost=2097152,  # 2 GB
        time_cost=4,  # 4 iterations
        parallelism=8,  # 8 threads
        hash_time="~2-5s",
    ),
}


class Settings(BaseSettings):
    """Application settings with validation and default values."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "BaliBlissed FastAPI Backend"
    DEBUG: bool = False

    # AI Configuration
    GEMINI_API_KEY: str | None = None
    AI_REQUEST_TIMEOUT: int = 60  # seconds
    AI_MAX_RETRIES: int = 2
    AI_RETRY_DELAY: float = 1.0  # seconds
    AI_BACKOFF_FACTOR: float = 2.0

    # Environment
    ENVIRONMENT: str = "development"
    LOG_TO_FILE: bool = True
    LOG_FILE: str = "logs/app.log"
    PRODUCTION_FRONTEND_URL: str | None = None

    # OAuth Settings
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    WECHAT_APP_ID: str | None = None
    WECHAT_APP_SECRET: str | None = None

    # Password Security
    PASSWORD_SECURITY_LEVEL: str = "standard"
    PASSWORD_HASHER_DEBUG: bool = False

    # Email Configuration
    # Path to the file downloaded from Google Cloud
    GMAIL_CLIENT_SECRET_FILE: Path = Path("secrets/client_secret.json")
    # Path where we will store the authorized user token (generated once)
    GMAIL_TOKEN_FILE: Path = Path("secrets/token.json")
    # The email address to send TO (your company email)
    # CHANGE THIS TO YOUR REAL EMAIL
    COMPANY_TARGET_EMAIL: str = "example@gmail.com"
    # Scopes required for the application
    GMAIL_SCOPES: list[str] = ["https://www.googleapis.com/auth/gmail.send"]

    # Database settings
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/baliblissed"
    DATABASE_ECHO: bool = False  # Set to True to log SQL queries

    # Database connection pool settings
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10
    POOL_TIMEOUT: int = 30
    POOL_RECYCLE: int = 3600  # Recycle connections after 1 hour

    # Security settings (SECRET_KEY validated to be secure in production)
    SECRET_KEY: str = "dev-only-insecure-key-replace-in-prod"  # noqa: S105
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "baliblissed-api"
    JWT_AUDIENCE: str = "baliblissed-client"

    # Account lockout settings
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # Pagination defaults
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100

    # Redis Configuration
    REDIS_ENABLED: bool = True
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    REDIS_URL: str | None = None
    RATE_LIMIT_DEFAULT_LIMITS: str = f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW}s"
    IN_MEMORY_FALLBACK_ENABLED: bool = True
    HEADERS_ENABLED: bool = True

    # Performance Configuration
    MAX_CONCURRENT_AI_REQUESTS: int = 10
    ENABLE_RESPONSE_CACHING: bool = True
    CACHE_TTL_ITINERARY: int = 86400  # 24 hours
    CACHE_TTL_QUERY: int = 3600  # 1 hour
    CACHE_TTL_CONTACT: int = 1800  # 30 minutes

    # Storage Configuration
    STORAGE_PROVIDER: Literal["local", "cloudinary"] = "local"
    UPLOADS_DIR: Path = Path("uploads")

    # Cloudinary Configuration (required when STORAGE_PROVIDER=cloudinary)
    CLOUDINARY_CLOUD_NAME: str | None = None
    CLOUDINARY_API_KEY: str | None = None
    CLOUDINARY_API_SECRET: str | None = None

    # Profile Picture Settings
    PROFILE_PICTURE_MAX_SIZE_MB: int = 5
    PROFILE_PICTURE_MAX_DIMENSION: int = 1024
    PROFILE_PICTURE_QUALITY: int = 85
    PROFILE_PICTURE_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]

    @field_validator("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")
    @classmethod
    def validate_cloudinary_config(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Ensure Cloudinary credentials are set when using cloudinary storage."""
        storage_provider = info.data.get("STORAGE_PROVIDER", "local")
        if storage_provider == "cloudinary" and not v:
            msg = f"{info.field_name} is required when STORAGE_PROVIDER=cloudinary"
            raise ValueError(msg)
        return v

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL."""
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def validate_redis_password_in_prod(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Ensure Redis password is set in production environment."""
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and not v:
            msg = "REDIS_PASSWORD is required in production environment!"
            raise ValueError(msg)
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """Ensure SECRET_KEY is set and secure."""
        if not v or v == "your-secret-key-change-this-in-production":
            env = info.data.get("ENVIRONMENT", "development")
            if env == "production":
                msg = "SECRET_KEY must be set to a secure value in production!"
                raise ValueError(msg)
        if len(v) < 32:
            env = info.data.get("ENVIRONMENT", "development")
            if env == "production":
                msg = "SECRET_KEY must be at least 32 characters in production!"
                raise ValueError(msg)
        return v


settings = Settings()


class RedisConfig(BaseSettings):
    """Redis cache configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    host: str = settings.REDIS_HOST
    port: int = settings.REDIS_PORT
    db: int = settings.REDIS_DB
    password: str | None = settings.REDIS_PASSWORD
    url: str | None = settings.REDIS_URL
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
    key_prefix: str = "cache"
    compression_enabled: bool = True
    compression_threshold: int = 1024  # bytes
    strategy: Literal["LRU", "FIFO"] = "LRU"
    enable_statistics: bool = True
    cleanup_interval: int = 300  # 5 minutes


redis_config = RedisConfig()
# Build redis connection pool kwargs dynamically
pool_kwargs: dict[str, Any] = {
    "host": redis_config.host,
    "port": redis_config.port,
    "db": redis_config.db,
    "password": redis_config.password,
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
# Only pass ssl if True to avoid compatibility issues
if redis_config.ssl:
    pool_kwargs["ssl"] = True


class LimiterConfig(BaseModel):
    """Configuration for rate limiting."""

    default_limits: list[str] = [settings.RATE_LIMIT_DEFAULT_LIMITS]
    storage_uri: str = settings.redis_url
    in_memory_fallback_enabled: bool = settings.IN_MEMORY_FALLBACK_ENABLED
    headers_enabled: bool = settings.HEADERS_ENABLED

    model_config = ConfigDict(from_attributes=True)


def get_context(level: str) -> CryptContext:
    """
    Get CryptContext configured for specified security level.

    Args:
        level: Security level to use

    Returns:
        CryptContext: Configured context

    Example:
        >>> ctx = get_context("high")
        >>> hashed = ctx.hash("password")

    """
    config = CONFIG_MAP[level]

    return CryptContext(
        schemes=["argon2", "pbkdf2_sha256"],
        deprecated="pbkdf2_sha256",
        argon2__memory_cost=config.memory_cost,
        argon2__time_cost=config.time_cost,
        argon2__parallelism=config.parallelism,
    )


def print_config_info() -> None:
    """Print detailed information about all security levels."""
    rprint("\n" + "[yellow]=[yellow]" * 80)
    rprint("[b i blue]Password Hashing Configuration Guide[b i blue]")
    rprint("[yellow]=[yellow]" * 80)

    for level, config in CONFIG_MAP.items():
        mem_cost: int = config.memory_cost
        rprint(f"\n[b green]{level.upper()}:[b green]")
        rprint("[yellow]=[yellow]" * 80)
        rprint(
            f"\t[i blue]Description:[i blue]        [green]{config.description}[green]",
        )
        rprint(
            f"\t[i blue]Memory Cost:[i blue]        [green]{mem_cost:,} bytes ({mem_cost // (1024 * 1024)}MB)[green]",
        )
        rprint(
            f"\t[i blue]Time Cost:[i blue]          [green]{config.time_cost} iterations[green]",
        )
        rprint(
            f"\t[i blue]Parallelism:[i blue]        [green]{config.parallelism} threads[green]",
        )
        rprint(
            f"\t[i blue]Estimated Time:[i blue]     [green]{config.hash_time}[green]",
        )

    rprint("\n" + "[yellow]=[yellow]" * 80)
    rprint("[b i blue]Recommendations:[b i blue]")
    rprint("[yellow]=[yellow]" * 80)
    rprint("""
  DEVELOPMENT:
    Use for local testing and development
    Fastest option for rapid iteration

  STANDARD (default):
    Use for most production applications
    Good balance of security and performance
    Suitable for web applications with normal load

  HIGH:
    Use for sensitive applications (banking, health)
    Higher security with acceptable performance
    Monitor system load when under heavy authentication

  PARANOID:
    Use only for extremely sensitive systems
    Maximum brute-force resistance
    May impact user experience during login
    Consider using only for initial password setup

Parameters Explanation:
  - Memory Cost: Higher = harder for GPU/ASIC attacks
  - Time Cost: More iterations = harder to brute-force
  - Parallelism: More threads = better performance on multi-core systems
    """)


if __name__ == "__main__":
    print_config_info()
