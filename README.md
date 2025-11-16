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
- **Management Routes**: Built-in endpoints for cache inspection and management

## Installation

### Prerequisites

- Python 3.13+
- Redis 6.0+

### Setup

- Clone or download the project:

```bash
cd fastapi-redis-cache
```

- Install dependencies (requires Python environment):

```bash
pip install -e ".[dev]"
```

Or install specific dependencies:

```bash
pip install fastapi redis pydantic pydantic-settings slowapi httpx pytest pytest-asyncio
```

## Quick Start

### Basic Usage

```python
from fastapi import FastAPI
from src import setup_cache, add_cache_routes, cached

app = FastAPI()

# Setup cache
cache_manager = setup_cache(app)

# Add cache management routes
add_cache_routes(app, cache_manager)

# Use cached decorator on endpoints
@app.get("/items")
@cached(cache_manager, ttl=600, namespace="items")
async def get_items():
    return {"items": []}
```

### Configuration

```python
from src import ApplicationConfig, RedisCacheConfig, CacheConfig

config = ApplicationConfig(
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

cache_manager = setup_cache(app, config)
```

## Decorators

### @cached - Cache endpoint results

```python
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
@app.post("/items")
@cache_busting(cache_manager, keys=["items_list"], namespace="items")
async def create_item(item: Item):
    # Invalidates the items_list cache entry
    return item

# With custom key builder
@app.put("/items/{item_id}")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "items_list"],
    namespace="items",
)
async def update_item(item_id: int, item: Item):
    return item
```

## Cache Manager API

```python
# Set value
await cache_manager.set(key, value, ttl=3600, namespace="items")

# Get value
value = await cache_manager.get(key, namespace="items")

# Delete keys
deleted = await cache_manager.delete(key1, key2, namespace="items")

# Check existence
exists = await cache_manager.exists(key1, key2, namespace="items")

# Get or set (cache-aside pattern)
value = await cache_manager.get_or_set(
    key,
    callback=lambda: expensive_operation(),
    ttl=3600,
    force_refresh=False
)

# TTL operations
ttl = await cache_manager.ttl(key)
await cache_manager.expire(key, seconds=3600)

# Clear all cache
await cache_manager.clear()

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
- `key_prefix`: Prefix for all cache keys (default: "cache:")
- `compression_enabled`: Enable compression (default: False)
- `compression_threshold`: Min size for compression in bytes (default: 1024)
- `strategy`: Eviction strategy "LRU" or "FIFO" (default: "LRU")
- `enable_statistics`: Track statistics (default: True)

## Environment Variables

Configure via environment variables with appropriate prefixes:

```bash
# Redis configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your-password
REDIS_SSL=false

# Cache configuration
CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400
CACHE_COMPRESSION_ENABLED=false
CACHE_COMPRESSION_THRESHOLD=1024

# Application configuration
ENVIRONMENT=production
DEBUG=false
```

## Error Handling

All exceptions inherit from `CacheException`:

```python
from src import CacheException, RedisConnectionError

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
pytest tests/ --cov=src --cov-report=html
```

## Best Practices

1. **Use namespaces**: Organize cache entries by feature

   ```python
   await cache_manager.set(key, value, namespace="users")
   ```

2. **Set appropriate TTLs**: Balance freshness and performance

   ```python
   @cached(cache_manager, ttl=300)  # 5 minutes for frequently updated data
   ```

3. **Implement cache busting**: Invalidate related caches on mutations

   ```python
   @cache_busting(cache_manager, keys=["users_list"])
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
   try:
       cached_value = await cache_manager.get(key)
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

## Example Application

See `example_app.py` for a complete working example with:

- Full CRUD operations
- Caching decorators
- Cache busting
- Rate limiting with SlowAPI
- Cache management endpoints

Run the example:

```bash
python example_app.py
```

Then visit `http://localhost:8000/docs` for interactive API documentation.

## Contributing

Contributions welcome! Please ensure:

- All code follows PEP 8 and Ruff rules
- Full type hints are provided
- Tests cover new functionality
- Documentation is updated

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions, please refer to the project repository.
