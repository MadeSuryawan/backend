# Architecture

## Overview

The FastAPI Redis Cache implementation is designed with a modular, multi-layered architecture that emphasizes separation of concerns, maintainability, and performance.

## Module Structure

```plaintext
app/
├── __init__.py
├── main.py                 # FastAPI app setup and main endpoints
├── clients/
│   └── redis_client.py     # Redis connection management
├── configs/
│   └── settings.py         # Pydantic configuration models
├── data/
│   └── statistics.py       # Cache statistics tracking
├── decorators/
│   └── caching.py          # @cached and @cache_busting decorators
├── errors/
│   └── exceptions.py       # Custom exception classes
├── managers/
│   └── cache_manager.py    # Core cache logic and operations
├── middleware/
│   └── middleware.py       # Request/response middleware and lifespan
├── routes/
│   └── cache.py            # Cache management API routes
└── utils/
    ├── cache_serializer.py # Serialization and compression
    └── helpers.py          # Utility functions
```

## Core Components

### 1. Configuration Layer (`app/configs/settings.py`)

Pydantic-based settings management for:

- **Settings**: Top-level application configuration.
- **RedisCacheConfig**: Redis connection parameters.
- **CacheConfig**: Cache behavior settings (TTL, compression, etc.).

Benefits include environment variable support, type validation, and runtime safety.

### 2. Client Layer (`app/clients/redis_client.py`)

An async wrapper around the `redis-py` library that provides:

- Robust connection pooling.
- Graceful error handling and health checks.
- Type-safe, low-level Redis commands (`get`, `set`, `delete`).

### 3. Utilities Layer (`app/utils/`)

- **`cache_serializer.py`**: Handles JSON serialization/deserialization and optional GZIP compression for cached values. It uses a marker to distinguish compressed data.
- **`helpers.py`**: Contains miscellaneous utility functions, including loggers and request processors.

### 4. Data Layer (`app/data/statistics.py`)

A thread-safe class for tracking cache statistics:

- Hits and misses.
- Cache operations (set, delete).
- Bytes read/written.
- Hit rate calculation.

### 5. Manager Layer (`app/managers/cache_manager.py`)

The `CacheManager` is the heart of the caching system, providing a high-level API for all caching operations:

```python
# Core operations
await cache_manager.get(key, namespace)
await cache_manager.set(key, value, ttl, namespace, compress)
await cache_manager.delete(key, namespace)
await cache_manager.exists(key)

# Advanced operations
await cache_manager.get_or_set(key, callback, ttl, namespace, force_refresh)
await cache_manager.expire(key, seconds)
await cache_manager.ttl(key)
await cache_manager.clear(namespace)

# Lifecycle and monitoring
await cache_manager.initialize()
await cache_manager.shutdown()
cache_manager.get_statistics()
```

It integrates the Redis client, serializer, and statistics tracker to provide a cohesive caching service.

### 6. Decorators Layer (`app/decorators/caching.py`)

Provides easy-to-use decorators for applying caching logic to FastAPI endpoints:

- **`@cached`**: Automatically caches the result of an endpoint.
- **`@cache_busting`**: Invalidates one or more cache keys when a mutation endpoint (e.g., POST, PUT, DELETE) is called.

Both decorators support custom key generation logic through `key_builder` functions.

### 7. Middleware & Lifespan (`app/middleware/middleware.py`)

- **Lifespan Manager**: The `lifespan` function handles the application's startup and shutdown events, ensuring that the `CacheManager` and its connection pool are initialized and closed gracefully.
- **Standard Middleware**: Includes middleware for request logging, security headers, CORS, and GZip compression.

### 8. Routes Layer (`app/routes/cache.py`)

Exposes administrative API endpoints for managing and monitoring the cache:

- `GET /cache/stats`: View current cache statistics.
- `GET /cache/ping`: Health check for the Redis connection.
- `DELETE /cache/clear`: Purge all keys from the cache.
- `POST /cache/clear/{namespace}`: Purge keys from a specific namespace.

## Data Flow

### Cache Hit Flow

```plaintext
Request
  ↓
@cached decorator
  ↓
Generate cache key
  ↓
CacheManager.get(key)
  ↓
RedisClient.get(key)
  ↓
Decompress (if needed) & Deserialize
  ↓
Return cached response to client
```

### Cache Miss Flow

```plaintext
Request
  ↓
@cached decorator
  ↓
Generate cache key
  ↓
CacheManager.get(key) → None
  ↓
Execute endpoint function
  ↓
Get result
  ↓
CacheManager.set(key, result)
  ↓
Serialize & Compress (if needed)
  ↓
RedisClient.set(key, value, ex=ttl)
  ↓
Return response to client
```

### Cache Busting Flow

```plaintext
Mutation Request (POST/PUT/DELETE)
  ↓
Execute endpoint function
  ↓
@cache_busting decorator
  ↓
Generate keys to invalidate
  ↓
CacheManager.delete(*keys)
  ↓
RedisClient.delete(*keys)
  ↓
Return response to client
```

## Error Handling Strategy

A hierarchy of custom exceptions (`app/errors/exceptions.py`) is used to handle cache-related failures gracefully.

```plaintext
Exception
  └─ CacheException (base)
      ├─ RedisConnectionError
      ├─ CacheKeyError
      ├─ CacheSerializationError
      └─ ...and others
```

The system is designed to be resilient; a cache failure will be logged but will not crash the application. The endpoint will execute as if it were a cache miss.
