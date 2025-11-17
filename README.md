# FastAPI Redis Cache

A seamless, production-ready Redis caching implementation for FastAPI with SlowAPI rate limiting support.

## Features

- **Async Redis Client**: Non-blocking Redis operations with connection pooling
- **Decorators**: Simple `@cached` and `@cache_busting` decorators for endpoints
- **Compression**: Optional GZIP compression for large cached values
- **Namespaces**: Organize cache entries by namespace
- **Statistics**: Built-in cache hit/miss tracking and metrics
- **TTL Management**: Flexible TTL configuration per operation
- **SlowAPI Integration**: Works seamlessly with existing rate limiters
- **Type Hints**: Full type hints for better IDE support
- **Error Handling**: Comprehensive exception handling and logging
- **In-Memory Fallback**: Automatically falls back to an in-memory cache if Redis is unavailable
- **Management Routes**: Built-in endpoints for cache inspection and management

## Installation

### Prerequisites

- Python 3.13+
- Redis 6.0+ (optional, for Redis caching)
- `uv` (recommended) or `pip`

### Setup

- Clone or download the project:

```bash
cd fastapi-redis-cache
```

- Install dependencies (requires Python environment):

```bash
# Using uv (recommended)
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

## Quick Start

### Basic Usage

```python
from fastapi import FastAPI
from app.decorators.caching import cached
from app.managers.cache_manager import CacheManager
from app.routes.cache import add_cache_routes

app = FastAPI()

# Setup cache
cache_manager = CacheManager()

# Add cache management routes
add_cache_routes(app, cache_manager)

# Use cached decorator on endpoints
@app.get("/items")
@cached(cache_manager, ttl=600, namespace="items")
async def get_items():
    # This endpoint will be cached. If Redis is down, it will use the in-memory cache.
    return {"items": []}
```

### Configuration

```python
from app.configs.settings import Settings, RedisCacheConfig, CacheConfig

config = Settings(
    debug=False,
    environment="production",
    redis=RedisCacheConfig(
        host="redis.example.com",
        port=6379,
        db=0,
        password="your-password",
        ssl=True,
    ),
    cache=CacheConfig(
        default_ttl=3600,
        max_ttl=86400,
        compression_enabled=True,
        compression_threshold=1024,
    ),
)

# The cache_manager should be initialized with the config, typically in the lifespan event
# For demonstration, assuming it's already configured globally or passed in.
# cache_manager.initialize(config.redis, config.cache)
```

## In-Memory Fallback

If the Redis server is unavailable upon application startup, the `CacheManager` will automatically fall back to a simple in-memory cache. This ensures that the application can continue to function without a hard dependency on Redis, although the cache will be non-persistent and local to each application instance.

- **Automatic**: No configuration is needed to enable the fallback.
- **Resilience**: Your application remains operational even if Redis is down.
- **Testing**: The fallback mechanism is thoroughly tested using mocking to simulate Redis connection failures.

## Decorators

### @cached - Cache endpoint results

```python
from app.decorators.caching import cached

@app.get("/items/{item_id}")
@cached(cache_manager, ttl=300, namespace="items")
async def get_item(item_id: int):
    # Results cached for 5 minutes
    return {"id": item_id, "name": "Item"}
```

Custom key builder:

```python
@cached(
    cache_manager,
    ttl=300,
    key_builder=lambda item_id, **kw: f"item_{item_id}"
)
async def get_item(item_id: int):
    return {"id": item_id}
```

### @cache_busting - Invalidate cache on mutations

```python
from app.decorators.caching import cache_busting

@app.post("/items")
@cache_busting(cache_manager, namespace="items") # Clears the entire 'items' namespace
async def create_item(item: dict):
    # Invalidates the 'items' namespace
    return item

# With custom key builder to bust specific keys
@app.put("/items/{item_id}")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "items_list"], # Busts specific item and a list
    namespace="items",
)
async def update_item(item_id: int, item: dict):
    return item
```

## Cache Manager API

```python
# Set value
await cache_manager.set(key, value, ttl=3600, namespace="items")

# Get value
value = await cache_manager.get(key, namespace="items")

# Delete keys (can take multiple keys)
deleted = await cache_manager.delete(key1, key2, namespace="items")

# Check existence (can take multiple keys)
exists = await cache_manager.exists(key1, key2, namespace="items")

# Get or set (cache-aside pattern)
value = await cache_manager.get_or_set(
    key,
    callback=lambda: expensive_operation(),
    ttl=3600,
    namespace="items", # Added namespace for consistency
    force_refresh=False
)

# TTL operations
ttl = await cache_manager.ttl(key, namespace="items") # Added namespace
await cache_manager.expire(key, seconds=3600, namespace="items") # Added namespace

# Clear all cache in a namespace
await cache_manager.clear(namespace="items") # Added namespace

# Health check
is_alive = await cache_manager.ping()

# Statistics
stats = cache_manager.get_statistics()
cache_manager.reset_statistics()
```

## Management Routes

The following routes are automatically added:

- `GET /cache/stats` - Get cache statistics (hits, misses, etc.)
- `GET /cache/ping` - Check if cache server is reachable
- `DELETE /cache/clear` - Clear all cache entries
- `POST /cache/clear/{namespace}` - Clear all cache entries within a specific namespace
- `GET /cache/reset-stats` - Reset statistics

## Integration with SlowAPI

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/items")
@limiter.limit("100/minute")
@cached(cache_manager, ttl=600, namespace="items")
async def get_items(request):
    return {"items": []}
```

## Configuration Options

### RedisCacheConfig

- `host`: Redis hostname (default: "localhost")
- `port`: Redis port (default: 6379)
- `db`: Redis database number (default: 0)
- `password`: Redis password (default: None)
- `ssl`: Use SSL connection (default: False)
- `socket_timeout`: Socket timeout in seconds (default: 5.0)
- `socket_connect_timeout`: Connection timeout in seconds (default: 5.0)
- `socket_keepalive`: Enable keepalive (default: True)
- `health_check_interval`: Health check interval in seconds (default: 30)
- `max_connections`: Max connection pool size (default: 50)
- `decode_responses`: Decode responses as strings (default: True)

### CacheConfig

- `default_ttl`: Default TTL in seconds (default: 3600)
- `max_ttl`: Maximum allowed TTL (default: 86400)
- `namespace_prefix`: Prefix for all cache keys (default: "fastapi-cache")
- `compression_enabled`: Enable compression (default: True)
- `compression_threshold`: Min size for compression in bytes (default: 1024)
- `statistics_enabled`: Track statistics (default: True)

## Environment Variables

Configure via environment variables with appropriate prefixes:

```bash
# Application configuration
APP_NAME="FastAPI Redis Cache"
DESCRIPTION="A production-ready caching solution for FastAPI."
DEBUG=true
LOG_TO_FILE=true
ENVIRONMENT="development"
PRODUCTION_FRONTEND_URL="https://your-frontend.com"

# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-password
REDIS_SSL=false

# Cache configuration
CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400
CACHE_NAMESPACE_PREFIX="fastapi-cache"
CACHE_COMPRESSION_ENABLED=true
CACHE_COMPRESSION_THRESHOLD=1024
CACHE_STATISTICS_ENABLED=true
```

## Error Handling

All exceptions inherit from `CacheException` (defined in `app/errors/exceptions.py`):

```python
from app.errors.exceptions import CacheException, RedisConnectionError
from logging import getLogger

logger = getLogger(__name__)

try:
    value = await cache_manager.get(key)
except RedisConnectionError as e:
    logger.exception(f"Redis connection failed: {e}")
except CacheException as e:
    logger.exception(f"Cache operation failed: {e}")
```

## Testing

Run tests with pytest:

```bash
pytest tests/ -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

### In-Memory Cache and Fallback Testing

The in-memory cache is tested in `tests/test_memory_client.py`, which covers all of its methods.

The fallback mechanism is tested in `tests/test_cache_manager.py` in the `test_cache_manager_fallback_to_memory` test. This test uses `unittest.mock.patch` to simulate a `RedisConnectionError` being raised when the `RedisClient.connect` method is called. This forces the `CacheManager` to fall back to the `MemoryClient`, and the test then asserts that the `CacheManager` is using the `MemoryClient` and that caching operations still work as expected.

## Best Practices

1. **Use namespaces**: Organize cache entries by feature

   ```python
   await cache_manager.set(key, value, namespace="users")
   ```

2. **Set appropriate TTLs**: Balance freshness and performance

   ```python
   @cached(cache_manager, ttl=300, namespace="data")  # 5 minutes for frequently updated data
   ```

3. **Implement cache busting**: Invalidate related caches on mutations

   ```python
   @cache_busting(cache_manager, namespace="users") # Clears the entire 'users' namespace
   async def update_user(user_id: int):
       pass
   ```

4. **Monitor statistics**: Track cache performance

   ```python
   stats = cache_manager.get_statistics()
   print(f"Hit rate: {stats['hit_rate']}")
   ```

5. **Handle cache failures gracefully**: Don't let cache errors break your app

   ```python
   from app.errors.exceptions import CacheException

   try:
       cached_value = await cache_manager.get(key, namespace="data")
   except CacheException:
       cached_value = None
   ```

## Performance Considerations

- Connection pooling: Configured with up to 50 connections
- Compression: Reduce memory usage for large values
- Namespaces: Organize keys for better scanning
- TTL: Prevent cache bloat with appropriate expiration
- Statistics: Minimal overhead, can be disabled if needed

## Security

- Redis connection pooling prevents connection exhaustion
- Password authentication supported
- SSL/TLS support for encrypted connections
- Type hints prevent injection attacks
- Input validation through Pydantic

## License

MIT License - See LICENSE file for details
