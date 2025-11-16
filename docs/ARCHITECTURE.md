# Architecture

## Overview

The FastAPI Redis Cache implementation is designed with a modular, layered architecture that emphasizes separation of concerns and maintainability.

## Module Structure

```plain text
src/
├── __init__.py              # Main package exports
├── config.py                # Configuration models
├── exceptions.py            # Custom exceptions
├── types.py                 # Type definitions
├── redis_client.py          # Redis connection management
├── serializer.py            # Serialization/compression
├── statistics.py            # Cache statistics
├── cache_manager.py         # Core cache logic
├── decorators.py            # FastAPI decorators
└── fastapi_integration.py   # FastAPI setup helpers
```

## Core Components

### 1. Configuration Layer (`config.py`)

Pydantic-based configuration models for:

- **RedisCacheConfig**: Redis connection parameters
- **CacheConfig**: Cache behavior settings
- **ApplicationConfig**: Overall application configuration

Benefits:

- Environment variable support
- Type validation
- IDE autocompletion
- Runtime safety

### 2. Redis Client (`redis_client.py`)

Async wrapper around `redis-py` providing:

- Connection pooling
- Error handling
- Type safety
- Health checks
- Information retrieval

Key features:

- Automatic connection management
- Graceful error handling
- Detailed logging
- Connection reuse

### 3. Serialization (`serializer.py`)

JSON serialization with optional compression:

- **Serialize**: Python objects → JSON strings
- **Deserialize**: JSON strings → Python objects
- **Compress**: GZIP compression for large values
- **Decompress**: GZIP decompression with marker detection

Compression:

- Opt-in per operation
- Configurable threshold
- Marker-based detection
- Base64 encoding for safety

### 4. Statistics (`statistics.py`)

Thread-safe statistics tracking:

- Hits and misses
- Cache operations (set, delete)
- Evictions
- Errors
- Bytes read/written
- Hit rate calculation

Thread safety:

- Lock-based synchronization
- Safe concurrent access
- No race conditions

### 5. Cache Manager (`cache_manager.py`)

High-level cache operations:

```python
# Core operations
await cache_manager.get(key, namespace)
await cache_manager.set(key, value, ttl, namespace, compress)
await cache_manager.delete(*keys, namespace)
await cache_manager.exists(*keys, namespace)

# Advanced operations
await cache_manager.get_or_set(key, callback, ttl, namespace, force_refresh)
await cache_manager.expire(key, seconds, namespace)
await cache_manager.ttl(key, namespace)
await cache_manager.clear(namespace)

# Utilities
await cache_manager.ping()
cache_manager.get_statistics()
cache_manager.reset_statistics()
```

Key features:

- Namespace support
- Configurable TTL
- Optional compression
- Automatic serialization
- Error resilience

### 6. Decorators (`decorators.py`)

Two main decorators:

#### @cached

```python
@cached(
    cache_manager,
    ttl=600,
    namespace="items",
    key_builder=optional_function,
    compress=True
)
async def get_items():
    return {}
```

Features:

- Automatic key generation or custom builder
- Miss handling with callback execution
- Result caching
- Hit tracking

#### @cache_busting

```python
@cache_busting(
    cache_manager,
    keys=["list", "count"],
    namespace="items",
    key_builder=optional_function
)
async def update_item(item_id):
    return {}
```

Features:

- Selective cache invalidation
- Custom key builders
- Mutation support (POST, PUT, DELETE)

### 7. FastAPI Integration (`fastapi_integration.py`)

Four main functions:

#### setup_cache(app, config)

- Initializes cache manager
- Sets up lifespan events
- Returns configured manager

#### add_cache_routes(app, cache_manager)

Adds management endpoints:

- `GET /cache/stats` - Statistics
- `GET /cache/ping` - Health check
- `DELETE /cache/clear` - Cache purge
- `GET /cache/reset-stats` - Stats reset

#### create_cache_error_handler(app)

Global exception handler for `CacheException`

#### CacheMiddleware

Extensible middleware for request/response caching

## Data Flow

### Cache Hit Flow

```plain text
Request
  ↓
@cached decorator
  ↓
Generate cache key
  ↓
cache_manager.get(key)
  ↓
RedisClient.get(key)
  ↓
Deserialize + Decompress
  ↓
Return to client
```

### Cache Miss Flow

```plain text
Request
  ↓
@cached decorator
  ↓
Generate cache key
  ↓
cache_manager.get(key) → None
  ↓
Execute endpoint function
  ↓
Serialize + Compress
  ↓
cache_manager.set(key, value)
  ↓
RedisClient.set(key, value, ex=ttl)
  ↓
Return to client
```

### Cache Busting Flow

```plain text
Mutation Request (POST/PUT/DELETE)
  ↓
@cache_busting decorator
  ↓
Execute endpoint function
  ↓
Generate keys to bust
  ↓
cache_manager.delete(*keys)
  ↓
RedisClient.delete(*keys)
  ↓
Return result to client
```

## Type Safety

Full type hints throughout:

```python
from src.types import CacheValue, CacheKey, CacheCallback

# Explicit types for clarity
async def get(self, key: CacheKey) -> CacheValue:
    ...

async def set(self, key: CacheKey, value: CacheValue, ex: int | None = None) -> bool:
    ...

async def get_or_set(
    self,
    key: CacheKey,
    callback: CacheCallback,
) -> CacheValue:
    ...
```

## Error Handling Strategy

Hierarchical exception structure:

```plain text
Exception
  └─ CacheException (base)
      ├─ RedisConnectionError
      ├─ CacheKeyError
      ├─ CacheSerializationError
      ├─ CacheDeserializationError
      ├─ CacheCompressionError
      ├─ CacheDecompressionError
      └─ RateLimitError
```

### Error Recovery

- Connection failures → Graceful degradation
- Serialization errors → Logged, not cached
- Compression errors → Uncompressed fallback
- Statistics recording → Regardless of success

## Performance Optimization

### Connection Pooling

- Up to 50 concurrent connections
- Automatic reuse
- Health checks (30-second interval)
- Graceful cleanup

### Compression

- Threshold-based (default 1KB)
- GZIP algorithm
- Base64 encoding
- Transparent detection

### Namespace Isolation

- Prefix-based key organization
- Efficient scoping
- No cross-contamination

### Statistics

- Minimal overhead
- Lock-free reads (by design)
- Atomic operations
- Thread-safe tracking

## Security Features

### Input Validation

- Pydantic model validation
- Type checking
- Environment variable parsing

### Connection Security

- SSL/TLS support
- Password authentication
- Socket timeout configuration
- Keepalive protection

### Data Protection

- Serialization validation
- Compression integrity
- Marker-based detection
- Error isolation

## Extension Points

### Custom Key Builder

```python
def custom_key_builder(*args, **kwargs) -> str:
    # Custom logic
    return f"prefix:{args[0]}:{kwargs['id']}"

@cached(cache_manager, key_builder=custom_key_builder)
async def endpoint(id: int):
    pass
```

### Custom Serializer

```python
class CustomSerializer:
    @staticmethod
    def serialize(value: Any) -> str:
        # Custom serialization
        pass

    @staticmethod
    def deserialize(value: str) -> Any:
        # Custom deserialization
        pass
```

### Middleware Extension

```python
class CustomCacheMiddleware(CacheMiddleware):
    async def __call__(self, request):
        # Pre-request logic
        response = await self.app(request)
        # Post-request logic
        return response
```

## Testing Strategy

### Unit Tests

- Cache manager operations
- Serialization/deserialization
- Statistics tracking
- Error handling

### Integration Tests

- API endpoints
- Cache decorators
- Rate limiting
- Cache busting

### Test Coverage

- Core logic: 100%
- Decorators: 95%+
- Integration: 90%+

## Deployment Considerations

### Environment Setup

```bash
REDIS_HOST=redis-prod.example.com
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=secure-password
REDIS_SSL=true

CACHE_DEFAULT_TTL=3600
CACHE_MAX_TTL=86400
CACHE_COMPRESSION_ENABLED=true

ENVIRONMENT=production
DEBUG=false
```

### Monitoring

- Hit rate tracking
- Error rate monitoring
- Connection pool health
- Memory usage tracking

### Scaling

- Horizontal scaling with shared Redis
- Connection pool sizing per instance
- TTL tuning for dataset size
- Namespace isolation per service

## Best Practices

1. **Always use namespaces** for organizational clarity
2. **Set appropriate TTLs** based on data freshness requirements
3. **Monitor statistics** to optimize cache strategy
4. **Implement cache busting** for all mutations
5. **Handle cache failures** gracefully in application logic
6. **Use compression** for large, infrequently-accessed data
7. **Test cache scenarios** in development and staging
8. **Review logs** for cache-related errors and warnings
