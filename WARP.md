# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

FastAPI Redis Cache - A production-ready Redis caching integration for FastAPI with SlowAPI rate limiting support. This library provides seamless caching decorators, compression, namespace management, and statistics tracking.

## Development Commands

### Setup & Installation

```bash
# Install all dependencies (including dev dependencies)
pip install -e ".[dev]"

# Or using uv (recommended)
uv pip install -e ".[dev]"
```

### Running the Application

```bash
# Run with uvicorn directly (development mode with auto-reload)
python main.py

# Or run with uvicorn command
uvicorn app:app --reload --host 127.0.0.1 --port 8000

# Access API documentation at http://localhost:8000/docs
```

### Testing

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=app --cov-report=html
pytest tests/ --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_cache_manager.py -v

# Run specific test function
pytest tests/test_cache_manager.py::test_cache_get -v
```

### Code Quality

```bash
# Lint with ruff (check for issues)
ruff check .

# Format code with ruff
ruff format .

# Fix auto-fixable issues
ruff check --fix .
```

## Architecture

### Core Components

**Multi-Layer Architecture:**

1. **Routes Layer** (`app/routes/`) - FastAPI endpoints for cache management
2. **Decorators Layer** (`app/decorators/`) - `@cached` and `@cache_busting` decorators
3. **Manager Layer** (`app/managers/`) - CacheManager with high-level cache operations
4. **Client Layer** (`app/clients/`) - RedisClient wrapper with connection pooling
5. **Configuration Layer** (`app/configs/`) - Pydantic-based settings
6. **Utilities Layer** (`app/utils/`) - Serialization, compression, helpers

### Key Design Patterns

**Caching Decorators:**

- `@cached`: Automatically caches endpoint results with configurable TTL and namespaces
- `@cache_busting`: Invalidates specific cache entries on mutations (POST/PUT/DELETE)
- Custom key builders: Functions that generate cache keys from endpoint arguments

**Namespace Isolation:**
Cache entries are organized by namespace (e.g., "items", "users") to prevent key collisions and enable targeted cache clearing.

**Connection Pooling:**
Redis client maintains a connection pool (default 50 connections) with health checks every 30 seconds for optimal performance.

**Compression Strategy:**
Optional GZIP compression for values exceeding threshold (default 1KB) with automatic detection/decompression.

**Statistics Tracking:**
Thread-safe tracking of hits, misses, operations, bytes read/written, and hit rates.

### Data Flow

**Cache Hit:**
Request → @cached decorator → Generate key → CacheManager.get() → RedisClient.get() → Deserialize/Decompress → Return

**Cache Miss:**
Request → @cached decorator → Generate key → CacheManager.get() returns None → Execute endpoint → Serialize/Compress → CacheManager.set() → RedisClient.set() → Return

**Cache Busting:**
Mutation request → Execute endpoint → @cache_busting decorator → Generate keys → CacheManager.delete() → RedisClient.delete()

## Important Code Patterns

### Using Cache Decorators

```python
# Basic caching with TTL and namespace
@app.get("/items/{item_id}")
@cached(cache_manager, ttl=300, namespace="items")
async def get_item(item_id: int) -> Item:
    return fetch_item(item_id)

# Custom key builder
@cached(
    cache_manager,
    ttl=600,
    key_builder=lambda item_id, **kw: f"item_{item_id}"
)
async def get_item(item_id: int) -> Item:
    return fetch_item(item_id)

# Cache busting on mutations
@app.post("/items")
@cache_busting(cache_manager, keys=["get_all_items"], namespace="items")
async def create_item(item: Item) -> Item:
    return save_item(item)

# Dynamic cache busting with key builder
@app.put("/items/{item_id}")
@cache_busting(
    cache_manager,
    key_builder=lambda item_id, **kw: [f"item_{item_id}", "get_all_items"],
    namespace="items"
)
async def update_item(item_id: int, item: ItemUpdate) -> Item:
    return update_item_in_db(item_id, item)
```

### SlowAPI Rate Limiting Integration

The decorators work seamlessly with SlowAPI. Apply rate limiting before caching:

```python
@app.get("/items")
@limiter.limit("100/minute")  # Apply rate limit first
@cached(cache_manager, ttl=600, namespace="items")
async def get_items(request: Request) -> dict:
    return {"items": fetch_all_items()}
```

### Environment Configuration

Configure via environment variables or `.env` file:

- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`, `REDIS_SSL`
- `CACHE_DEFAULT_TTL`, `CACHE_MAX_TTL`, `CACHE_COMPRESSION_ENABLED`, `CACHE_COMPRESSION_THRESHOLD`
- `ENVIRONMENT`, `DEBUG`

See `docs/CONFIGURATION.md` for comprehensive configuration options.

## Project-Specific Rules

### Code Standards

- **Type Annotations Required**: All functions must have complete type hints (enforced by Ruff ANN rules)
- **Line Length**: 100 characters max (Ruff configured)
- **Docstrings**: Required for all public modules, classes, and functions (Pydocstyle D rules)
- **Import Ordering**: Use isort with "app" as first-party package

### Async Patterns

- All cache operations are async and must be awaited
- Use `async def` for all endpoint functions
- Never block the event loop with synchronous operations

### Error Handling

- All custom exceptions inherit from `CacheException` (see `app/errors/exceptions.py`)
- Cache failures should be logged but not break application flow
- Use try/except with specific exception types, avoid bare except

### Testing Requirements

- Tests use `pytest-asyncio` with auto mode
- Coverage target: 90%+ for core logic
- Test files follow pattern: `test_*.py`
- Use fixtures for common setup (cache_manager, redis_client)

## Redis Requirements

**Local Development:**

```bash
# Start Redis with Docker
docker run -d -p 6379:6379 redis:latest

# Or with Docker Compose (if you create docker-compose.yml)
docker-compose up -d redis
```

Redis must be running on `localhost:6379` (default) or configured via environment variables.

## Common Gotchas

1. **Request Object in Decorators**: When using `@limiter.limit()` with `@cached`, endpoints must accept `request: Request` parameter even if not used
2. **Key Builder Signatures**: Custom key builders receive `*args` and `**kwargs` from the endpoint function - filter carefully
3. **Serialization**: Only JSON-serializable objects can be cached - Pydantic models work via `.model_dump()`
4. **Namespace Best Practice**: Always use namespaces to organize cache entries logically
5. **TTL Limits**: TTL is automatically capped at `CACHE_MAX_TTL` (default 86400 seconds/24 hours)

## Documentation

- `docs/ARCHITECTURE.md` - Detailed architecture and component documentation
- `docs/CONFIGURATION.md` - Complete configuration reference
- `docs/QUICKSTART.md` - Quick start guide
- `README.md` - User-facing documentation with usage examples

## Additional Notes

- Python 3.13+ required
- Package manager: `uv` (modern alternative to pip)
- Logging: Configured with file logger in `logs/` directory
- The project uses SlowAPI for rate limiting, which integrates with the caching system
