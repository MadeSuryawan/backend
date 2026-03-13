"""
Application settings and configuration constants.

This module contains the core Settings class with environment-specific
orchestration logic for the BaliBlissed backend application.
"""

from os import environ
from pathlib import Path
from typing import Literal
from warnings import warn

from argon2 import PasswordHasher
from pydantic import ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path().cwd() / "secrets" / ".env"


class Settings(BaseSettings):
    """Application settings with validation and default values."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "BaliBlissed FastAPI Backend"
    DEBUG: bool = False

    # Server Configuration
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    REQUEST_TIMEOUT: int = 30
    MAX_REQUEST_SIZE_MB: int = 10

    # API Documentation
    DOCS_ENABLED: bool = True

    # Monitoring & Metrics
    ENABLE_METRICS: bool = False

    # OpenTelemetry Configuration
    OTEL_CONSOLE_EXPORT_ENABLED: bool = False  # Export traces to console (useful for debugging)

    # Environment
    ENVIRONMENT: str = "development"
    LOG_TO_FILE: bool = True
    LOG_FILE: str = "logs/app.log"
    LOG_EXCLUDED_PATHS: str = "/metrics,/health,/health/live,/health/ready,/favicon.ico"
    PRODUCTION_FRONTEND_URL: str | None = None

    # Localization
    TZ: str = "Asia/Makassar"

    # AI Configuration
    GEMINI_API_KEY: str | None = None
    AI_REQUEST_TIMEOUT: int = 60  # seconds
    AI_MAX_RETRIES: int = 2
    AI_RETRY_DELAY: float = 1.0  # seconds
    AI_BACKOFF_FACTOR: float = 2.0
    AI_SAFETY_THRESHOLD: Literal["none", "low", "medium", "high"] = "medium"

    # OAuth Settings
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    WECHAT_APP_ID: str | None = None
    WECHAT_APP_SECRET: str | None = None
    OAUTH_STATE_EXPIRE_SECONDS: int = 600  # 10 minutes for state token

    # Password Security
    # Security level for password hashing (development, standard, high, paranoid)
    PASSWORD_SECURITY_LEVEL: str = "standard"
    PASSWORD_HASHER_DEBUG: bool = False
    # Dummy hash for timing attack protection - MUST be set in production
    # Used when verifying passwords for users with no password (e.g., OAuth-only accounts)
    # to ensure consistent timing regardless of whether the user has a password hash
    # Format: Pre-generated argon2id hash of a random string
    # Example: argon2id$v=19$m=65536,t=3,p=4$... (use: python -c "from argon2 import PasswordHasher; print(PasswordHasher(time_cost=2, memory_cost=524288, parallelism=2).hash('your-secret-dummy-string'))")
    PASSWORD_DUMMY_HASH: str = "$argon2id$v=19$m=524288,t=2,p=2$3xo9Wpo4Kn0qjXSq3G2Yew$ojdbsjAnpbHjY+Z98yxePPCxR1IJBb9oupN0bCSI0c0"

    # Trusted Hosts (for security middleware)
    # Includes testserver and test for unit testing
    TRUSTED_HOSTS: str = "localhost,127.0.0.1,0.0.0.0,testserver,test"

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

    # SMTP Configuration (fallback email provider)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True
    SMTP_FROM_EMAIL: str | None = None
    SMTP_FROM_NAME: str = "BaliBlissed"

    # Database settings
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/baliblissed"
    DATABASE_ECHO: bool = False  # Set to True to log SQL queries

    # Database connection pool settings
    # POOL_SIZE: base connections kept open per process.  Set to 10 so each of
    # the 4 production workers has headroom without exhausting the pool under
    # moderate concurrency.
    # MAX_OVERFLOW: extra connections allowed above POOL_SIZE during bursts.
    # POOL_TIMEOUT: seconds to wait for a connection before raising; kept low
    # so callers get a fast, explicit error rather than hanging for 30 s.
    POOL_SIZE: int = 10
    MAX_OVERFLOW: int = 5
    POOL_TIMEOUT: int = 10
    POOL_RECYCLE: int = 1800  # Recycle connections after 30 minutes

    # Security settings (SECRET_KEY validated to be secure in production)
    SECRET_KEY: str = "dev-only-insecure-key-replace-in-prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "baliblissed-api"
    JWT_AUDIENCE: str = "baliblissed-client"

    # Account lockout settings
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15

    # Email Verification Settings
    VERIFICATION_TOKEN_EXPIRE_HOURS: int = 24  # 24 hours
    VERIFICATION_RESEND_LIMIT: int = 3  # Max resends per 24 hours
    FRONTEND_URL: str = "http://localhost:3000"  # Override in production

    # Password Reset Settings
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS: int = 1  # 1 hour
    PASSWORD_RESET_RESEND_LIMIT: int = 3  # Max reset requests per hour

    # Pagination defaults
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100

    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://localhost:8000"

    # Redis Configuration
    REDIS_ENABLED: bool = True
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_USERNAME: str | None = None  # Redis ACL username (Redis 6+)
    REDIS_PASSWORD: str | None = None
    REDIS_URL: str | None = None

    # Redis SSL/TLS Configuration (Production)
    REDIS_SSL: bool = False  # Enable SSL/TLS connection
    REDIS_SSL_CA_CERTS: str | None = None  # Path to CA certificates file
    REDIS_SSL_CA_PATH: str | None = None  # Path to CA certs directory (see docs)
    REDIS_SSL_CERT_REQS: str = "required"  # none, optional, required
    REDIS_SSL_CERTFILE: str | None = None  # Path to client certificate
    REDIS_SSL_KEYFILE: str | None = None  # Path to client private key
    REDIS_SSL_CHECK_HOSTNAME: bool = True  # Verify hostname matches certificate

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

    # IP Geolocation API Configuration
    IP_GEOLOCATION_API_KEY: str | None = None

    # Profile Picture Settings
    PROFILE_PICTURE_MAX_SIZE_MB: int = 5
    PROFILE_PICTURE_MAX_DIMENSION: int = 1024
    PROFILE_PICTURE_QUALITY: int = 85
    PROFILE_PICTURE_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]

    # Media Upload Settings (for reviews and blogs)
    MEDIA_IMAGE_MAX_SIZE_MB: int = 5
    MEDIA_IMAGE_MAX_COUNT_REVIEW: int = 5
    MEDIA_IMAGE_MAX_COUNT_BLOG: int = 10
    MEDIA_VIDEO_MAX_SIZE_MB: int = 50
    MEDIA_VIDEO_MAX_COUNT_BLOG: int = 3
    MEDIA_IMAGE_ALLOWED_TYPES: list[str] = ["image/jpeg", "image/png", "image/webp"]
    MEDIA_VIDEO_ALLOWED_TYPES: list[str] = ["video/mp4", "video/webm", "video/quicktime"]

    # Health Check Configuration
    HEALTH_CHECK_ENABLED: bool = True
    HEALTH_CHECK_ENDPOINT: str = "/health"

    # Monitoring & Error Tracking
    SENTRY_DSN: str | None = None
    SENTRY_ENVIRONMENT: str = "development"
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # OpenTelemetry Configuration
    OTEL_TRACES_SAMPLER_ARG: float = 0.1

    # Webhook Configuration
    WEBHOOK_SECRET: str | None = None

    # Feature Flags
    FEATURE_REGISTRATION_ENABLED: bool = True
    FEATURE_AI_CHAT_ENABLED: bool = True
    FEATURE_EMAIL_VERIFICATION_REQUIRED: bool = True

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
        # Build auth part with username and password
        auth_parts = []
        if self.REDIS_USERNAME:
            auth_parts.append(self.REDIS_USERNAME)
        if self.REDIS_PASSWORD:
            auth_parts.append(self.REDIS_PASSWORD)
        auth = ":".join(auth_parts) + "@" if auth_parts else ""
        protocol = "rediss" if self.REDIS_SSL else "redis"
        return f"{protocol}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def validate_redis_password_in_prod(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Ensure Redis password is set in production environment."""
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and not v:
            msg = "REDIS_PASSWORD is required in production environment!"
            raise ValueError(msg)
        return v

    @field_validator("REDIS_SSL")
    @classmethod
    def validate_redis_ssl_in_prod(cls, v: bool, info: ValidationInfo) -> bool:  # noqa: FBT001
        """Warn if SSL is not enabled in production environment."""
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and not v:
            warn(
                "REDIS_SSL is disabled in production. It is strongly recommended "
                "to enable SSL/TLS for Redis connections in production environments.",
                stacklevel=2,
            )
        return v

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
        """Ensure SECRET_KEY is set and secure."""
        insecure_defaults = {
            "your-secret-key-change-this-in-production",
            "dev-only-insecure-key-replace-in-prod",
        }
        if not v or v in insecure_defaults:
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

    @field_validator("DOCS_ENABLED")
    @classmethod
    def validate_docs_in_prod(cls, v: bool, info: ValidationInfo) -> bool:  # noqa: FBT001
        """Warn if API docs are enabled in production."""
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and v:
            warn(
                "DOCS_ENABLED is true in production. It's recommended to disable "
                "API documentation (Swagger/ReDoc) in production for security.",
                stacklevel=2,
            )
        return v

    @field_validator("TRUSTED_HOSTS")
    @classmethod
    def validate_trusted_hosts_in_prod(cls, v: str, info: ValidationInfo) -> str:
        """Ensure TRUSTED_HOSTS is properly configured in production."""
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production" and (not v or v == "localhost,127.0.0.1,0.0.0.0"):
            warn(
                "TRUSTED_HOSTS is using default development values in production. "
                "Please configure TRUSTED_HOSTS with your production domain(s).",
                stacklevel=2,
            )
        return v

    @property
    def trusted_hosts_list(self) -> list[str]:
        """Get TRUSTED_HOSTS as a list of strings."""
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS_ORIGINS as a list of strings."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def log_excluded_paths_list(self) -> list[str]:
        """Get LOG_EXCLUDED_PATHS as a list of strings."""
        return [path.strip() for path in self.LOG_EXCLUDED_PATHS.split(",") if path.strip()]

    @field_validator("PASSWORD_DUMMY_HASH")
    @classmethod
    def validate_password_dummy_hash(cls, v: str, info: ValidationInfo) -> str:
        """
        Ensure PASSWORD_DUMMY_HASH is set and valid.

        In production, this MUST be explicitly set to ensure consistent timing behavior.
        In development, a hash will be auto-generated if not provided.

        The dummy hash should be a pre-generated argon2id hash of a random string.
        Generate one with:
            python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('your-random-string'))"

        Args:
            v: The provided dummy hash value
            info: Pydantic validation info

        Returns:
            The validated dummy hash

        Raises:
            ValueError: If not set in production environment
        """
        env = info.data.get("ENVIRONMENT", "development")
        is_production = env in ("production", "prod")

        if not v:
            if is_production:
                # In production, require explicit configuration
                msg = (
                    "PASSWORD_DUMMY_HASH must be explicitly set in production! "
                    'Generate one with: python -c "from argon2 import PasswordHasher; '
                    "print(PasswordHasher().hash('your-random-string'))\""
                )
                raise ValueError(msg)
            # In development, auto-generate with warning
            warn(
                "PASSWORD_DUMMY_HASH not set - auto-generating for development. "
                "This should be explicitly configured in production for consistent timing behavior.",
                stacklevel=2,
            )
            v = PasswordHasher(time_cost=2, memory_cost=524288, parallelism=2).hash(
                "@baliblised@dummy@hash",
            )
            return v

        return v


settings = Settings()

# Set timezone for consistent datetime handling
environ["TZ"] = settings.TZ
