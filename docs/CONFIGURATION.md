# Configuration Guide

## Overview

FastAPI Redis Cache can be configured through:

1. Python code (recommended for type safety)
2. Environment variables
3. .env files
4. Hybrid approach

## Configuration Classes

### ApplicationConfig

Top-level configuration container.

```python
from src import ApplicationConfig

config = ApplicationConfig(
    app_name="My FastAPI App",
    debug=False,
    environment="production",
    redis=RedisCacheConfig(...),
    cache=CacheConfig(...),
)
```

### RedisCacheConfig

Redis connection and client settings.

```python
from src import RedisCacheConfig

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
    
    # Data Handling
    decode_responses=True,         # Decode responses as strings
    encoding="utf-8",              # Response encoding
)
```

### CacheConfig

Cache behavior and feature settings.

```python
from src import CacheConfig

cache_config = CacheConfig(
    # TTL Settings
    default_ttl=3600,              # Default cache TTL in seconds (1 hour)
    max_ttl=86400,                 # Maximum allowed TTL (24 hours)
    
    # Key Prefixing
    key_prefix="cache:",           # Prefix for all cache keys
    
    # Compression
    compression_enabled=False,     # Enable GZIP compression
    compression_threshold=1024,    # Minimum size for compression (bytes)
    
    # Eviction
    strategy="LRU",                # "LRU" or "FIFO" eviction strategy
    
    # Monitoring
    enable_statistics=True,        # Enable cache statistics tracking
    cleanup_interval=300,          # Cleanup interval in seconds
)
```

## Environment Variables

Configure via environment variables with specific prefixes.

### Redis Configuration

```bash
# Connection
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-secure-password
REDIS_SSL=true

# Timeouts
REDIS_SOCKET_TIMEOUT=5.0
REDIS_SOCKET_CONNECT_TIMEOUT=5.0
REDIS_SOCKET_KEEPALIVE=true
REDIS_HEALTH_CHECK_INTERVAL=30

# Connection Pool
REDIS_MAX_CONNECTIONS=50

# Data Handling
REDIS_DECODE_RESPONSES=true
REDIS_ENCODING=utf-8
```

### Cache Configuration

```bash
# TTL Settings
CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400

# Key Prefixing
CACHE_KEY_PREFIX=cache:

# Compression
CACHE_COMPRESSION_ENABLED=true
CACHE_COMPRESSION_THRESHOLD=1024

# Eviction
CACHE_STRATEGY=LRU

# Monitoring
CACHE_ENABLE_STATISTICS=true
CACHE_CLEANUP_INTERVAL=300
```

### Application Configuration

```bash
# General
APP_NAME=FastAPI Redis Cache App
DEBUG=false
ENVIRONMENT=production
```

## Configuration Examples

### Development Configuration

```python
from src import ApplicationConfig, RedisCacheConfig, CacheConfig

dev_config = ApplicationConfig(
    debug=True,
    environment="development",
    redis=RedisCacheConfig(
        host="localhost",
        port=6379,
        socket_timeout=1.0,  # Quick timeout for debugging
    ),
    cache=CacheConfig(
        default_ttl=600,  # 10 minutes for dev
        compression_enabled=False,  # Easier debugging
        enable_statistics=True,  # Track performance
    ),
)
```

### Production Configuration

```python
from src import ApplicationConfig, RedisCacheConfig, CacheConfig

prod_config = ApplicationConfig(
    debug=False,
    environment="production",
    redis=RedisCacheConfig(
        host="redis.production.local",
        port=6379,
        db=0,
        password="secure-password-here",
        ssl=True,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        health_check_interval=30,
        max_connections=100,
    ),
    cache=CacheConfig(
        default_ttl=3600,  # 1 hour
        max_ttl=86400,  # 24 hours
        key_prefix="prod:cache:",
        compression_enabled=True,
        compression_threshold=512,  # Compress larger values
        strategy="LRU",
        enable_statistics=True,
    ),
)
```

### Staging Configuration

```python
from src import ApplicationConfig, RedisCacheConfig, CacheConfig

staging_config = ApplicationConfig(
    debug=False,
    environment="staging",
    redis=RedisCacheConfig(
        host="redis.staging.local",
        port=6379,
        db=1,
        password="staging-password",
        ssl=True,
        socket_timeout=3.0,
        max_connections=75,
    ),
    cache=CacheConfig(
        default_ttl=1800,  # 30 minutes
        max_ttl=43200,  # 12 hours
        key_prefix="staging:cache:",
        compression_enabled=True,
        compression_threshold=768,
    ),
)
```

### High-Performance Configuration

```python
from src import ApplicationConfig, RedisCacheConfig, CacheConfig

highperf_config = ApplicationConfig(
    environment="production",
    redis=RedisCacheConfig(
        host="redis-cluster.internal",
        port=6379,
        db=0,
        password="secure-password",
        ssl=True,
        socket_timeout=2.0,
        socket_connect_timeout=2.0,
        socket_keepalive=True,
        health_check_interval=10,  # Frequent health checks
        max_connections=200,  # More connections
    ),
    cache=CacheConfig(
        default_ttl=7200,  # 2 hours
        max_ttl=604800,  # 7 days
        key_prefix="perf:cache:",
        compression_enabled=True,
        compression_threshold=256,  # Compress more aggressively
        strategy="LRU",
        enable_statistics=True,
    ),
)
```

## .env File Example

Create a `.env` file in your project root:

```bash
# Application
ENVIRONMENT=production
DEBUG=false
APP_NAME=My FastAPI Application

# Redis Connection
REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=my-secure-password-123
REDIS_SSL=true

# Redis Timeouts
REDIS_SOCKET_TIMEOUT=5.0
REDIS_SOCKET_CONNECT_TIMEOUT=5.0
REDIS_SOCKET_KEEPALIVE=true

# Redis Pool
REDIS_MAX_CONNECTIONS=50

# Cache Behavior
CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400
CACHE_KEY_PREFIX=cache:

# Compression
CACHE_COMPRESSION_ENABLED=true
CACHE_COMPRESSION_THRESHOLD=1024

# Monitoring
CACHE_ENABLE_STATISTICS=true
```

Load in your application:

```python
from dotenv import load_dotenv
from src import ApplicationConfig

# Load environment variables from .env
load_dotenv()

# Create config (automatically loads from environment)
config = ApplicationConfig()
```

## Runtime Configuration

### Programmatic Override

```python
from src import ApplicationConfig, RedisCacheConfig

# Base configuration
config = ApplicationConfig()

# Override specific settings
config.redis.host = "new-redis-host.com"
config.redis.ssl = True
config.cache.default_ttl = 7200

# Or create fresh config with overrides
config = ApplicationConfig(
    environment="production",
    redis=RedisCacheConfig(
        host="redis-prod.local",
        password="secure-password",
    ),
)
```

### Per-Request Configuration

```python
from fastapi import FastAPI, Depends
from src import CacheManager, ApplicationConfig

app = FastAPI()

@app.get("/items")
async def get_items(ttl: int = Depends(lambda: 600)):
    # Use custom TTL from query parameter
    return {"ttl": ttl}
```

## Configuration Validation

All configurations are validated using Pydantic:

```python
from src import ApplicationConfig, RedisCacheConfig

try:
    config = ApplicationConfig(
        redis=RedisCacheConfig(
            port=-1,  # Invalid port
        ),
    )
except ValueError as e:
    print(f"Configuration error: {e}")
```

## Configuration Best Practices

### 1. Environment-Specific Configs

```python
import os
from src import ApplicationConfig

env = os.getenv("ENVIRONMENT", "development")

if env == "production":
    config = ApplicationConfig(
        debug=False,
        environment="production",
        # Production settings
    )
elif env == "staging":
    config = ApplicationConfig(
        debug=False,
        environment="staging",
        # Staging settings
    )
else:
    config = ApplicationConfig(
        debug=True,
        environment="development",
        # Development settings
    )
```

### 2. Secrets Management

Use environment variables for sensitive data:

```bash
# .env (git-ignored)
REDIS_PASSWORD=${REDIS_SECRET}

# Or via environment
export REDIS_PASSWORD="secure-password-from-vault"
```

### 3. Feature Toggles

```python
from src import CacheConfig
import os

config = CacheConfig(
    compression_enabled=os.getenv("ENABLE_COMPRESSION", "true").lower() == "true",
    enable_statistics=os.getenv("ENABLE_STATS", "true").lower() == "true",
)
```

### 4. Performance Tuning

Based on expected load:

```python
from src import RedisCacheConfig

# For low traffic
low_traffic = RedisCacheConfig(
    max_connections=25,
    socket_timeout=10.0,
)

# For high traffic
high_traffic = RedisCacheConfig(
    max_connections=200,
    socket_timeout=2.0,
    health_check_interval=10,
)
```

### 5. Configuration Logging

```python
import logging
from src import ApplicationConfig

config = ApplicationConfig()
logger = logging.getLogger(__name__)

logger.info(f"Redis Config: {config.redis}")
logger.info(f"Cache Config: {config.cache}")
logger.info(f"Environment: {config.environment}")
```

## Troubleshooting

### Connection Issues

If you get connection errors:

```python
# Increase timeouts
config.redis.socket_timeout = 10.0
config.redis.socket_connect_timeout = 10.0

# Check host and port
print(f"Connecting to {config.redis.host}:{config.redis.port}")
```

### Performance Issues

If cache is slow:

```python
# Disable compression for small values
config.cache.compression_enabled = False

# Increase pool size
config.redis.max_connections = 100

# Increase health check interval
config.redis.health_check_interval = 60
```

### Memory Issues

If Redis memory is growing:

```python
# Reduce default TTL
config.cache.default_ttl = 1800  # 30 minutes

# Enable compression
config.cache.compression_enabled = True
config.cache.compression_threshold = 256  # More aggressive
```
