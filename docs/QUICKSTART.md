# Quick Start Guide

Get started with FastAPI Redis Cache in 5 minutes!

## Prerequisites

- Python 3.13 or higher
- Redis 6.0 or higher
- Redis server running locally or accessible

## Installation

- **Clone the project**

```bash
cd fastapi-redis-cache
```

- **Install dependencies**

```bash
pip install -e ".[dev]"
```

## Running the Example

- **Start Redis** (if not already running):

```bash
# Using Docker
docker run -d -p 6379:6379 redis:latest

# Or using local Redis installation
redis-server
```

- **Run the example application**:

```bash
python example_app.py
```

- **Visit the API documentation**:

Open your browser to `http://localhost:8000/docs`

## Basic Usage

### 1. Simple Caching

```python
from fastapi import FastAPI
from src import setup_cache, cached

app = FastAPI()
cache_manager = setup_cache(app)

@app.get("/items")
@cached(cache_manager, ttl=600, namespace="items")
async def get_items():
    # This will be cached for 10 minutes
    return {"items": []}
```

### 2. Cache Busting on Updates

```python
from src import cache_busting

@app.post("/items")
@cache_busting(cache_manager, keys=["get_items"], namespace="items")
async def create_item(item: Item):
    # This will invalidate the get_items cache
    return item

@app.delete("/items/{item_id}")
@cache_busting(cache_manager, keys=["get_items"], namespace="items")
async def delete_item(item_id: int):
    # This will also invalidate the get_items cache
    return {"message": "Item deleted"}
```

### 3. Manual Cache Operations

```python
# Set value
await cache_manager.set("user_123", {"name": "John"}, ttl=3600)

# Get value
user = await cache_manager.get("user_123")

# Delete key
await cache_manager.delete("user_123")

# Clear all cache
await cache_manager.clear()
```

### 4. With Rate Limiting (SlowAPI)

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/items")
@limiter.limit("100/minute")
@cached(cache_manager, ttl=600)
async def get_items(request):
    return {"items": []}
```

## Testing the Cache

### Test 1: Cache Hit

```bash
# First request (cache miss)
curl http://localhost:8000/items

# Second request (cache hit) - should be instant
curl http://localhost:8000/items

# Check cache statistics
curl http://localhost:8000/cache/stats
```

### Test 2: Cache Busting

```bash
# Create an item (this busts the cache)
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "name": "Test Item", "price": 9.99}'

# Check statistics to see busted cache
curl http://localhost:8000/cache/stats
```

### Test 3: Rate Limiting

```bash
# Rapid requests (will hit rate limit after 100 requests in 1 minute)
for i in {1..101}; do
  curl http://localhost:8000/items
done
```

## Configuration

### Environment Variables

Create a `.env` file:

```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Cache
CACHE_DEFAULT_TTL=3600
CACHE_COMPRESSION_ENABLED=false

# App
ENVIRONMENT=development
DEBUG=true
```

### Python Configuration

```python
from src import ApplicationConfig, RedisCacheConfig, CacheConfig

config = ApplicationConfig(
    debug=True,
    environment="development",
    redis=RedisCacheConfig(
        host="localhost",
        port=6379,
    ),
    cache=CacheConfig(
        default_ttl=3600,
        compression_enabled=False,
    ),
)

cache_manager = setup_cache(app, config)
```

## Common Tasks

### Check Cache Health

```python
# Check if Redis is reachable
is_alive = await cache_manager.ping()
print(f"Redis status: {'Connected' if is_alive else 'Disconnected'}")
```

### Get Cache Statistics

```python
stats = cache_manager.get_statistics()
print(f"Hit rate: {stats['hit_rate']}")
print(f"Total hits: {stats['hits']}")
print(f"Total misses: {stats['misses']}")
```

### Clear Cache Manually

```python
# Clear all cache
await cache_manager.clear()

# Or via API
curl -X DELETE http://localhost:8000/cache/clear
```

### Reset Statistics

```python
# Clear statistics
cache_manager.reset_statistics()

# Or via API
curl http://localhost:8000/cache/reset-stats
```

## Debugging

### Enable Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("src")
```

### Check Cache Keys

```python
# Get cache statistics
stats = await cache_manager.get_statistics()
print(stats)

# Check if key exists
exists = await cache_manager.exists("my_key")
print(f"Key exists: {exists}")

# Check TTL
ttl = await cache_manager.ttl("my_key")
print(f"TTL: {ttl} seconds")
```

## Next Steps

1. **Read the full documentation**: See `README.md`
2. **Explore architecture**: See `docs/ARCHITECTURE.md`
3. **Configure for production**: See `docs/CONFIGURATION.md`
4. **Review the example app**: See `example_app.py`
5. **Run tests**: `pytest tests/`

## Troubleshooting

### Connection Refused

If you get "Connection refused":

1. Check Redis is running: `redis-cli ping`
2. Verify host and port in configuration
3. Check firewall rules

### Cache Not Working

If cache seems disabled:

1. Check statistics: `curl http://localhost:8000/cache/stats`
2. Verify Redis connection: `curl http://localhost:8000/cache/ping`
3. Check logs for errors

### Performance Issues

If cache seems slow:

1. Check Redis performance: `redis-cli --latency`
2. Monitor connection pool: Check `REDIS_MAX_CONNECTIONS` setting
3. Review cache hit rate: `curl http://localhost:8000/cache/stats`

## API Endpoints Reference

### Cache Management

- `GET /cache/stats` - Get cache statistics
- `GET /cache/ping` - Check cache connection
- `DELETE /cache/clear` - Clear all cache
- `GET /cache/reset-stats` - Reset statistics

### Example Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /items` - Get all items (cached)
- `GET /items/{item_id}` - Get item (cached)
- `POST /items` - Create item (cache busted)
- `PUT /items/{item_id}` - Update item (cache busted)
- `DELETE /items/{item_id}` - Delete item (cache busted)

## Support

For issues or questions:

1. Check the documentation
2. Review example code
3. Check logs for errors
4. Run tests to verify setup

Happy caching! 🚀
