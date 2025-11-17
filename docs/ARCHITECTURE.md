# Architecture

## Overview

The FastAPI Redis Cache implementation is designed with a modular, multi-layered architecture that emphasizes separation of concerns, maintainability, and performance. It includes a resilient in-memory fallback mechanism to ensure high availability.

## Module Structure

```plaintext
app/
├── __init__.py
├── main.py                 # FastAPI app setup and main endpoints
├── clients/
│   ├── redis_client.py     # Redis connection management
│   └── memory_client.py    # In-memory cache client (for fallback)
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

### 2. Client Layer (`app/clients/`)

- **`redis_client.py`**: An async wrapper around the `redis-py` library that provides robust connection pooling, graceful error handling, and type-safe, low-level Redis commands.
- **`memory_client.py`**: A simple, dictionary-based in-memory cache client that mimics the `RedisClient`'s API. It serves as a seamless, zero-configuration fallback when Redis is unavailable.

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

The `CacheManager` is the heart of the caching system, providing a high-level API for all caching operations. It orchestrates the clients, serializer, and statistics tracker.

**Key Responsibility**: During initialization, it attempts to connect to Redis. If the connection fails, it automatically switches to the `MemoryClient`, ensuring the caching functionality remains available.

### 6. Decorators Layer (`app/decorators/caching.py`)

Provides easy-to-use decorators for applying caching logic to FastAPI endpoints:

- **`@cached`**: Automatically caches the result of an endpoint.
- **`@cache_busting`**: Invalidates one or more cache keys when a mutation endpoint (e.g., POST, PUT, DELETE) is called.

### 7. Middleware & Lifespan (`app/middleware/middleware.py`)

- **Lifespan Manager**: The `lifespan` function handles the application's startup and shutdown events, ensuring that the `CacheManager` and its connection pool are initialized and closed gracefully.

### 8. Routes Layer (`app/routes/cache.py`)

Exposes administrative API endpoints for managing and monitoring the cache, which work with both Redis and the in-memory fallback.

## Data Flow

### Cache Initialization Flow

```plaintext
Application Startup
  ↓
Lifespan Event
  ↓
CacheManager.initialize()
  ↓
Attempt RedisClient.connect()
  ├── Success: Use RedisClient
  └── Failure (RedisConnectionError): Use MemoryClient (Fallback)
```

### Cache Hit Flow (Redis or In-Memory)

```plaintext
Request
  ↓
@cached decorator
  ↓
Generate cache key
  ↓
CacheManager.get(key)
  ↓
ActiveClient.get(key) (RedisClient or MemoryClient)
  ↓
Decompress (if needed) & Deserialize
  ↓
Return cached response to client
```

### Cache Miss Flow (Redis or In-Memory)

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
ActiveClient.set(key, value, ex=ttl)
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

The system is designed to be resilient. If Redis is the active client and a command fails, the error is logged, and the operation proceeds as a cache miss. If the `CacheManager` has fallen back to the in-memory cache, operations are generally safe from I/O errors.
