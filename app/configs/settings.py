"""Application settings and configuration constants.

This module contains application settings, constants, and configuration
values for the BaliBlissed backend application.
"""

from pathlib import Path
from typing import Literal

# from google.genai.types import (
#     GenerateContentConfig,
#     GoogleMaps,
#     GoogleSearch,
#     HarmBlockThreshold,
#     HarmCategory,
#     SafetySetting,
#     Tool,
# )
from pydantic import EmailStr, SecretStr
from pydantic_settings.main import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# --- Constants ---
MAX_QUERY_LENGTH = 1000
MAX_MESSAGE_LENGTH = 2000
MAX_DESTINATION_LENGTH = 100
MAX_NAME_LENGTH = 100
MIN_TRIP_DURATION = 1
MAX_TRIP_DURATION = 365
MAX_INTERESTS_COUNT = 20
MIN_MESSAGE_LENGTH = 10

WHATSAPP_NUMBER = "+6285847006743"

# Rate limiting constants
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# Response constants
DEFAULT_ERROR_MESSAGE = "An unexpected server error occurred."
ITINERARY_GENERATION_ERROR = "Failed to generate itinerary."
QUERY_PROCESSING_ERROR = "Failed to process query."
CONTACT_INQUIRY_ERROR = "Failed to process contact inquiry."

# AI Model Configuration
GEMINI_MODEL = "gemini-2.0-flash"

# Harm = HarmCategory
# Block = HarmBlockThreshold

# # Safety settings for content generation
# SAFETY_SETTINGS = [
#     SafetySetting(
#         category=Harm.HARM_CATEGORY_HARASSMENT,
#         threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
#     ),
#     SafetySetting(
#         category=Harm.HARM_CATEGORY_HATE_SPEECH,
#         threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
#     ),
#     SafetySetting(
#         category=Harm.HARM_CATEGORY_SEXUALLY_EXPLICIT,
#         threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
#     ),
#     SafetySetting(
#         category=Harm.HARM_CATEGORY_DANGEROUS_CONTENT,
#         threshold=Block.BLOCK_MEDIUM_AND_ABOVE,
#     ),
# ]

# tools = {
#     "function_declarations": None,
#     "retrieval": None,
#     "google_search": GoogleSearch(),
#     "google_search_retrieval": None,
#     "enterprise_web_search": None,
#     "google_maps": None,
#     "url_context": None,
#     "computer_use": None,
#     "code_execution": None,
# }

# GENERATION_CONFIG = GenerateContentConfig(
#     temperature=0.7,
#     top_p=0.8,
#     top_k=40,
#     max_output_tokens=4096 * 2,
#     response_mime_type="application/json",
#     system_instruction="You are a friendly customer service assistant for a Bali travel agency called BaliBlissed.",
#     safety_settings=SAFETY_SETTINGS,
#     # tools=[Tool(**tools)],
# )


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
    PRODUCTION_FRONTEND_URL: str | None = None

    # Email Configuration
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: SecretStr = SecretStr("")
    MAIL_FROM: EmailStr | str = ""
    MAIL_PORT: int = 587
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # Redis Configuration (optional)
    REDIS_ENABLED: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None

    # Performance Configuration
    MAX_CONCURRENT_AI_REQUESTS: int = 10
    ENABLE_RESPONSE_CACHING: bool = True
    CACHE_TTL_ITINERARY: int = 86400  # 24 hours
    CACHE_TTL_QUERY: int = 3600  # 1 hour
    CACHE_TTL_CONTACT: int = 1800  # 30 minutes


def no_api_key_error() -> None:
    """Raise error if GEMINI_API_KEY is not set."""
    mssg = "GEMINI_API_KEY is required but not set"
    raise ValueError(mssg)


def no_email_config_error() -> None:
    """Raise error if email configuration is not set."""
    mssg = "Email configuration (MAIL_USERNAME, MAIL_PASSWORD) is required"
    raise ValueError(mssg)


# Initialize settings from environment variables
# try:
#     settings = Settings()
#     # Validate critical settings
#     if not settings.GEMINI_API_KEY:
#         no_api_key_error()
#     if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
#         no_email_config_error()
# except Exception as e:
#     print(f"Configuration error: {e}")
#     raise
settings = Settings()


class RedisCacheConfig(BaseSettings):
    """Redis cache configuration."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", case_sensitive=False)

    host: str = settings.REDIS_HOST
    port: int = settings.REDIS_PORT
    db: int = settings.REDIS_DB
    password: str | None = settings.REDIS_PASSWORD
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
    compression_enabled: bool = True
    compression_threshold: int = 1024  # bytes
    strategy: Literal["LRU", "FIFO"] = "LRU"
    enable_statistics: bool = True
    cleanup_interval: int = 300  # 5 minutes
