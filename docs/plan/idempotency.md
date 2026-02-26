# Idempotency Implementation Plan

## 1. Objective and Context

The application utilizes a robust FastAPI architecture with a global retry policy (`@with_retry`), a comprehensive asynchronous caching system (`CacheManager` backed by Redis), and an integrated database setup using SQLModel/PostgreSQL. While retry mechanisms mitigate transient errors, blindly applying them to `POST` endpoints (like blog creation, user registration) or costly external calls (AI generation) can lead to data duplication, structural errors (like `UniqueConstraintViolation`), and duplicated financial costs.

This document outlines a comprehensive plan to implement true API idempotency to provide safe retries across the system, ensuring that duplicate requests yield consistent results without duplicate side effects.

## 2. Industry-Standard Approaches Analysis

### 2.1 Database Constraints (Unique Keys)

- **Description:** Using database-level unique constraints (e.g., unique indices on `(author_id, slug)` or a dedicated idempotency table).
- **Pros:** Guarantees absolute data consistency; no split-brain issues.
- **Cons:** High latency for cross-region setups; doesn't prevent side-effects like triggering emails or costly AI calls before the DB insert occurs.

### 2.2 Redis-Based Idempotency Keys (The Stripe Pattern)

- **Description:** The client sends an `Idempotency-Key` header with mutation requests (POST/PATCH/PUT). The server checks Redis before processing. If the key exists and the request is completed, the cached response is returned. If processing, it waits or rejects.
- **Pros:** Millisecond latency; protects against duplicate AI calls or third-party API dispatches; naturally scales horizontally; keys automatically expire (TTL setup).
- **Cons:** Requires a reliable distributed cache (which the current system already has).

### 2.3 Specific Recommendation Justified by Codebase Context

**Recommendation:** **Redis-Based Idempotency Keys via FastAPI Middleware/Dependencies.**

**Justification:** The codebase already heavily relies on Redis for caching endpoint responses (`@cached`, `@cache_busting`, `CacheManager`). An idempotency layer built on top of the existing `CacheManager` integrates seamlessly without introducing new infrastructure dependencies. It acts at the HTTP layer, naturally protecting downstream resources (database, AI services, external email services) from duplicate processing.

## 3. Implementation Strategy

The implementation will avoid unnecessary complexity by leveraging FastAPI Dependencies or Middleware, keeping business logic clean.

### Phase 1: Establish the Idempotency Manager

Create a dedicated `IdempotencyManager` extending or wrapping the existing `CacheManager` to handle atomic `SETNX` (Set if Not eXists) operations and response caching.

### Phase 2: Create a FastAPI Dependency

Create a dependency `get_idempotency_key` that enforces the presence of an `Idempotency-Key` header for mutation endpoints where duplicate execution is dangerous.

### Phase 3: Update Target Routes

Gradually apply the idempotency logic to critical `POST` endpoints (`app/routes/blog.py`, `app/routes/ai.py`, `app/routes/auth.py`).

### Concrete Code Example

**`app/managers/idempotency.py`**:

```python
from fastapi import Request, Response, Header, HTTPException
import orjson
from typing import Optional
from app.configs.settings import settings

async def check_idempotency(
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., description="Unique key for idempotent requests")
):
    if not idempotency_key or len(idempotency_key) < 16:
        raise HTTPException(status_code=400, detail="Valid Idempotency-Key header is required.")
        
    cache: CacheManager = request.app.state.cache_manager
    redis_key = f"idemp:{request.state.user.uuid}:{idempotency_key}"
    
    # Check if request is currently processing or completed
    cached_data = await cache.get(redis_key)
    
    if cached_data:
        if cached_data.get("status") == "processing":
            raise HTTPException(status_code=409, detail="Request is already processing.")
        
        # Request completed, return cached response
        cached_response = cached_data.get("response")
        response.status_code = cached_data.get("status_code", 200)
        return cached_response

    # Mark as processing (using atomic SET with NX if possible via CacheManager)
    # TTL set to 24 hours to prevent indefinite storage
    await cache.set(redis_key, {"status": "processing"}, ttl=86400)
    
    # Store key in request state so that a middleware/decorator can update it post-process
    request.state.idempotency_key = redis_key
    return idempotency_key
```

**Middleware/Decorator implementation (`app/decorators/idempotency.py`)**:
Wrap route handlers to catch the response and update the Redis key with `{"status": "completed", "response": response.body, "status_code": response.status_code}`.

## 4. Security Considerations

- **Token Validation & Scope:** The idempotency key must be scoped to the authenticated user (`user.uuid + idempotency_key`) to prevent malicious actors from guessing keys and stealing responses of other users.
- **Race Condition Prevention:** The check and set operation mapping the key to `"processing"` must be atomic. By using Redis `SET key value NX`, we ensure only the exact first request proceeds. Subsequent concurrent requests will receive a `409 Conflict`.
- **Malicious Duplicate Handling:** Enforce strict validation on the `Idempotency-Key` format (e.g., UUIDv4) to prevent injection or excessively long key names that could waste cache memory.

## 5. Scalability Analysis

- **Distributed System Challenges:** Redis is single-threaded and handles atomic sets properly. If scaling to a Redis Cluster, keys are appropriately partitioned since they map to specific user shards if hashtagging is used (e.g., `{user_id}:idemp_key`).
- **Storage Implications:** Idempotency keys consume memory. With a 24-hour TTL, storage is transient. Assuming 100,000 `POST` requests a day, at ~500 bytes per cached response/key pair, the memory overhead is around ~50MB natively in Redis, which is negligible.
- **Performance Optimization:** The lookup adds a network round-trip (~1-2ms) to Redis. Since Redis connections are pooled (via `core()` in `redis.asyncio`), this overhead is incredibly small compared to the cost of duplicate DB operations or AI calls.

## 6. Maintenance Considerations

- **Monitoring:** Track Cache Hits on the `idemp:` namespace. A high hit rate on idempotency indicates client-side retry storms or network instability that should be monitored via OpenTelemetry/Prometheus (already integrated in the app).
- **Debugging:** Centralized logging should inject the `Idempotency-Key` into the log context (via `Loguru`/`ContextMiddleware`) to trace single logical operations across multiple physical retries.
- **Future Extensibility:** The structure allows dropping in different backend storages for idempotency (like PostgreSQL JSONB) if Redis persistence becomes an issue, as long as it conforms to the interface.

## 7. Trade-off Decisions

| Decision | Rationale | Alternative Considered |
| -------- | -------- | -------- |
| **Redis vs Database storage** | Redis provides lower latency and native TTL. The app already relies on Redis, so it avoids DB table bloat. | Postgres `idempotency_keys` table. Rejected due to DB write overhead and required cleanup jobs. |
| **Strict 409 Conflict for concurrent requests** | Prevents race conditions right at the edge without putting load on the DB/AI clients. | Polling/waiting for the first request to finish. Rejected because it holds up connection worker threads in FastAPI. |
| **Mandatory Header for specific POSTs vs Global Middleware** | Applying it globally to all `POST/PATCH` might break endpoints that naturally allow repetition without keys. Opt-in via route dependency is safer. | Global middleware mapping. Rejected due to high risk of regressions on non-critical endpoints. |
| **User-scoped Keys** | Prevents Cross-User data leakage if identical keys are randomly generated or maliciously reused. | Global keys. Rejected due to severe security implications. |

## 8. Summary of Action Items for Implementation

1. Add `Idempotency-Key` header requirement to `POST /blogs/create`, `POST /auth/register`, and all `POST /ai/*` generation endpoints.
2. Implement `idempotent_request` dependency and middleware.
3. Update `docs/prompts/idempotency.md` to guide developers to use the new dependency instead of just removing `@with_retry`.
4. Add unit tests for `409 Conflict` on race conditions and testing expected response delivery on subsequent requests.
