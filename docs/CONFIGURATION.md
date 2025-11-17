# Configuration Guide

## Overview

The application is configured using Pydantic's `BaseSettings`, which allows for type-safe configuration management through environment variables, `.env` files, or direct instantiation.

## Configuration Classes (`app/configs/settings.py`)

### Settings

The top-level configuration container that orchestrates all other settings.

```python
from app.configs.settings import Settings

# This will automatically load from environment variables or a .env file
settings = Settings()
```

### RedisCacheConfig

Defines Redis connection and client settings.

```python
from app.configs.settings import RedisCacheConfig

redis_config = RedisCacheConfig(
    # Connection
    host="localhost",              # Redis server hostname
    port=6379,                     # Redis server port
    db=0,                          # Redis database number (0-15)
    password=None,                 # Redis password for authentication
    ssl=False,                     # Use SSL/TLS encryption
    
    # Timeouts
    socket_timeout=5.0,            # Socket timeout in seconds
    socket_connect_timeout=5.0,    # Connection timeout in seconds
    socket_keepalive=True,         # Enable TCP keepalive
    health_check_interval=30,      # Health check interval in seconds
    
    # Connection Pool
    max_connections=50,            # Maximum pool connections
)
```

### CacheConfig

Defines cache behavior and feature settings.

```python
from app.configs.settings import CacheConfig

cache_config = CacheConfig(
    # TTL Settings
    default_ttl=3600,              # Default cache TTL in seconds (1 hour)
    max_ttl=86400,                 # Maximum allowed TTL (24 hours)
    
    # Key Prefixing
    namespace_prefix="fastapi-cache", # Prefix for all cache keys
    
    # Compression
    compression_enabled=True,      # Enable GZIP compression
    compression_threshold=1024,    # Minimum size for compression (bytes)
    
    # Statistics
    statistics_enabled=True,       # Enable cache statistics tracking
)
```

## Environment Variables

Configure the application by setting environment variables. The variables are prefixed based on the configuration class they belong to.

### Application Settings

```bash
# General App Settings
APP_NAME="FastAPI Redis Cache"
DESCRIPTION="A production-ready caching solution for FastAPI."
DEBUG=true
LOG_TO_FILE=true
ENVIRONMENT="development"
PRODUCTION_FRONTEND_URL="https://your-frontend.com"
```

### Redis Configuration (`REDIS_` prefix)

```bash
# Connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-secure-password
REDIS_SSL=false

# Timeouts & Pool
REDIS_SOCKET_TIMEOUT=5.0
REDIS_SOCKET_CONNECT_TIMEOUT=5.0
REDIS_SOCKET_KEEPALIVE=true
REDIS_HEALTH_CHECK_INTERVAL=30
REDIS_MAX_CONNECTIONS=50
```

### Cache Configuration (`CACHE_` prefix)

```bash
# TTL Settings
CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400

# Key Prefixing
CACHE_NAMESPACE_PREFIX="fastapi-cache"

# Compression
CACHE_COMPRESSION_ENABLED=true
CACHE_COMPRESSION_THRESHOLD=1024

# Statistics
CACHE_STATISTICS_ENABLED=true
```

## `.env` File Example

Create a `.env` file in your project root to manage environment-specific configurations easily.

```dotenv
# Application
APP_NAME="My FastAPI App"
ENVIRONMENT=development
DEBUG=true
LOG_TO_FILE=true

# Redis Connection
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_SSL=false

# Redis Timeouts & Pool
REDIS_SOCKET_TIMEOUT=5.0
REDIS_MAX_CONNECTIONS=50

# Cache Behavior
CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400
CACHE_NAMESPACE_PREFIX="dev-cache"
CACHE_COMPRESSION_ENABLED=true
CACHE_COMPRESSION_THRESHOLD=1024
CACHE_STATISTICS_ENABLED=true
```

The `Settings` object will automatically load these values from the `.env` file upon initialization.

## Configuration Profiles Examples

### Development Configuration

For local development, a `.env` file is typically sufficient. The default values in `settings.py` are also geared towards a development environment.

### Production Configuration

In a production environment, you would typically set environment variables directly or use a secrets management system.

```bash
# Set these in your production environment
export ENVIRONMENT="production"
export DEBUG="false"
export LOG_TO_FILE="true"

export REDIS_HOST="prod-redis.my-cloud.com"
export REDIS_PASSWORD="a-very-secure-password"
export REDIS_SSL="true"
export REDIS_MAX_CONNECTIONS="100"

export CACHE_DEFAULT_TTL="1800" # 30 minutes
export CACHE_NAMESPACE_PREFIX="prod-api-cache"
```

## Configuration Best Practices

### 1. Use Environment Variables for Secrets

Never hardcode sensitive information like passwords. Always use environment variables or a secret management tool.

### 2. Environment-Specific Settings

Use different `.env` files (e.g., `.env.development`, `.env.production`) or environment variables to tailor the configuration to the specific environment (development, staging, production).

### 3. Performance Tuning

Adjust `REDIS_MAX_CONNECTIONS`, `CACHE_DEFAULT_TTL`, and compression settings based on your application's load and data characteristics. For high-traffic applications, consider increasing the connection pool size and fine-tuning TTLs.
