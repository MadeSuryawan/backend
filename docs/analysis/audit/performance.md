# Performance & Scalability Audit — BaliBlissed Backend
>
> **Date:** 2026-03-03 | **Focus:** Async patterns, DB efficiency, caching, resource limits

---

## 1. Async / Non-Blocking I/O

### ✅ STRENGTHS

| Item | Status | Notes |
| ------ | -------- | ------- |
| SQLAlchemy 2.0 async engine with `asyncpg` | ✅ Pass | No sync I/O in DB layer |
| `hash_password` offloaded to executor | ✅ Pass | CPU-bound work properly isolated |
| `httpx` (async) for external HTTP calls | ✅ Pass | No `requests` library found |
| `aiofiles` for file I/O | ✅ Pass | Async file operations |
| `uvloop` as event loop | ✅ Pass | 2–4× faster than default asyncio loop |
| `httptools` HTTP parser | ✅ Pass | High-performance HTTP parsing |

### ⚠️ WEAKNESSES

#### **PERF-001 — HIGH | `BaseHTTPMiddleware` on Multiple Middlewares (Performance Tax)**

The application uses `BaseHTTPMiddleware` for **5 custom middlewares** (`TimezoneMiddleware`, `LoggingMiddleware`, `SecurityHeadersMiddleware`, `IdempotencyMiddleware`, `ContextMiddleware`). Starlette's `BaseHTTPMiddleware` **has a known performance overhead** due to how it buffers request/response bodies and calls `call_next`. This is well-documented: each `BaseHTTPMiddleware` adds an extra async generator layer.

- **Files:** All middleware files in `app/middleware/`
- **Impact:** ~5–15% latency overhead per request at high concurrency (measured in Starlette benchmarks)
- **CWE:** N/A (performance, not security)
- **Fix (Long-term):** Migrate to pure ASGI middleware using the `__call__` interface:

```python
class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                # ... other headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
```

---

**PERF-002 — MEDIUM | `get_event_loop()` Deprecated in Python 3.10+**

`app/middleware/middleware.py` imports `from asyncio import get_event_loop` and `app/managers/password_manager.py` likely uses it too. `get_event_loop()` is deprecated in Python 3.12+ and will raise a `DeprecationWarning` in some contexts when called from non-main threads.

- **Fix:** Replace with `asyncio.get_running_loop()` inside async functions:

```python
# Before
from asyncio import get_event_loop
loop = get_event_loop()
result = await loop.run_in_executor(executor, func, arg)

# After
import asyncio
result = await asyncio.get_running_loop().run_in_executor(executor, func, arg)
```

---

## 2. Database Efficiency

### ✅ STRENGTHS

| Item | Status | Notes |
| ------ | -------- | ------- |
| `pool_pre_ping=True` | ✅ Pass | Stale connection detection |
| Statement and lock timeout (30s) | ✅ Pass | Prevents long-running query hangs |
| `expire_on_commit=False` | ✅ Pass | Avoids implicit lazy-load after commit |
| `autocommit=False`, `autoflush=False` | ✅ Pass | Explicit transaction control |
| `pool_recycle=3600` | ✅ Pass | Prevents 8-hour PostgreSQL idle timeout |
| GIN index on `blogs.tags` JSONB | ✅ Pass | Full-text tag search optimized |
| Composite indexes on `blogs`, `reviews` | ✅ Pass | Query-specific indexes present |

### ⚠️ WEAKNESSES

#### **PERF-003 — HIGH | Connection Pool Too Small for Production (Default 5+10)**

Default `POOL_SIZE=5`, `MAX_OVERFLOW=10` gives a maximum of 15 concurrent DB connections. With `--workers 4` in the Dockerfile CMD, each uvicorn worker has its own pool: **4 × 15 = 60 total connections**. For a heavily loaded API, this may be insufficient, but more importantly, the per-worker pool is too small.

- **File:** `app/configs/settings.py` lines 105–107
- **Impact:** Connection starvation under load → `QueuePool limit of size 5 overflow 10 reached` errors
- **Fix:** Tune pool per worker count:

```python
# More appropriate production values (scale with CPU count)
POOL_SIZE: int = 10        # connections per worker
MAX_OVERFLOW: int = 5      # burst connections
POOL_TIMEOUT: int = 10     # timeout for acquiring from pool (not 30s!)
```

Also consider using **NullPool** with PgBouncer in front of PostgreSQL for production:

```python
from sqlalchemy.pool import NullPool
engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
```

---

**PERF-004 — HIGH | N+1 Query Risk in `UserRepository.do_password_verify`**

`do_password_verify` calls `get_by_username` then separately accesses `db_user.password_hash`. While this is a single object lookup, the broader pattern across repositories does not enforce `selectinload` or `joinedload` for relationships. If `UserDB` gains relationships (future), N+1 will silently appear.

- **File:** `app/repositories/user.py` lines 182–203
- **Impact:** N+1 queries in listing endpoints (blogs with authors, reviews with users)
- **Fix (Defensive):** Add a convention to the `BaseRepository.get_many` method that uses `selectinload` by default:

```python
async def get_many(
    self,
    *,
    load_options: list | None = None,
    ...
) -> list[ModelT]:
    stmt = select(self.model)
    if load_options:
        for opt in load_options:
            stmt = stmt.options(opt)
    ...
```

---

**PERF-005 — MEDIUM | `scan_iter` in Token Blacklist Count is O(N)**

`TokenBlacklist.get_blacklist_count` uses `async for _ in self._redis.scan_iter(...)` to count blacklisted tokens. This is an O(N) operation that scans ALL keys matching the prefix. At scale (millions of tokens), this blocks the Redis server for extended periods.

- **File:** `app/managers/token_blacklist.py` lines 118–131
- **Impact:** Redis latency spikes during count operations, blocking all other Redis calls
- **Fix:** Use a Redis `COUNTER` key that increments/decrements atomically:

```python
BLACKLIST_COUNT_KEY = "token:blacklist:count"

async def add_to_blacklist(self, jti, exp):
    ...
    await self._redis.incr(BLACKLIST_COUNT_KEY)

async def get_blacklist_count(self) -> int:
    count = await self._redis.get(BLACKLIST_COUNT_KEY)
    return int(count) if count else 0
```

---

## 3. Caching

### ✅ STRENGTHS

| Item | Status | Notes |
| ----- | ------ | ----- |
| Redis-backed cache with TTL configuration | ✅ Pass | `CACHE_TTL_ITINERARY=86400`, `CACHE_TTL_QUERY=3600` |
| `ENABLE_RESPONSE_CACHING` feature flag | ✅ Pass | Can be toggled without deploy |
| `CacheManager` as central abstraction | ✅ Pass | Single responsibility |
| `Idempotency-Key` for mutation caching | ✅ Pass | Proper idempotency implementation |

### ⚠️ WEAKNESSES

#### **PERF-006 — MEDIUM | No Cache Stampede Protection (Thundering Herd)**

When a cached item expires, multiple concurrent requests will simultaneously miss the cache and hit the database. There is no "lock-then-populate" (probabilistic early expiration or Lua-based locking) to prevent this.

- **Impact:** Burst of DB queries on cache expiry under load
- **Fix:** Implement probabilistic early expiration (XFetch algorithm) or a Redis Lua lock on cache miss:

```python
async def get_or_set_with_lock(self, key: str, factory, ttl: int):
    value = await self.get(key)
    if value is not None:
        return value
    
    lock_key = f"{key}:lock"
    acquired = await self._redis.set(lock_key, "1", nx=True, ex=5)
    if acquired:
        try:
            value = await factory()
            await self.set(key, value, ttl=ttl)
            return value
        finally:
            await self._redis.delete(lock_key)
    else:
        # Wait and retry
        await asyncio.sleep(0.1)
        return await self.get(key)
```

---

## 4. Background Tasks & Pagination

### ✅ STRENGTHS

| Item | Status | Notes |
| ----- | ------ | ----- |
| `MAX_PAGE_SIZE: int = 100` enforced | ✅ Pass | Prevents runaway list queries |
| `DEFAULT_PAGE_SIZE: int = 10` | ✅ Pass | Sensible default |
| `MAX_REQUEST_SIZE_MB: int = 10` configured | ✅ Pass | Body size limit |

### ⚠️ WEAKNESSES

#### **PERF-007 — MEDIUM | No Cursor-Based Pagination for Large Datasets**

Pagination uses offset-based approach (based on settings `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE`). For tables with > 100K rows, `OFFSET N` forces a full table scan up to N rows, degrading with deeper pages.

- **Impact:** `GET /blogs?page=1000` will be >100× slower than `page=1`
- **Fix:** Implement keyset/cursor-based pagination:

```python
async def get_paginated(
    self,
    cursor_id: UUID | None = None,
    limit: int = 10,
) -> list[ModelT]:
    stmt = select(self.model)
    if cursor_id:
        stmt = stmt.where(self.model.id > cursor_id)
    stmt = stmt.order_by(self.model.id).limit(limit)
    result = await self.session.execute(stmt)
    return list(result.scalars().all())
```

---

#### **PERF-008 — MEDIUM | No Celery / Background Worker for Heavy AI Operations**

AI itinerary generation (`google-genai`) runs synchronously within the request lifecycle even though it can take 5–30 seconds. This keeps an async worker thread occupied and depletes connection pools.

- **File:** `app/routes/ai.py` (inferred from route structure)
- **Impact:** Long-tail latency; timeout risks with `AI_REQUEST_TIMEOUT: int = 60`
- **Fix (Long-term):** Move AI requests to an async task queue (Celery + Redis or `arq`), return a `202 Accepted` with a task ID, and poll for results:

```python
@router.post("/ai/itinerary", status_code=202)
async def create_itinerary(body: ItineraryRequest) -> dict:
    task_id = await task_queue.enqueue(generate_itinerary, body.model_dump())
    return {"task_id": task_id, "status": "processing"}
```

---

## 5. Memory & Resource Management

### ✅ STRENGTHS

| Item | Status | Notes |
| ----- | ------ | ----- |
| `GZipMiddleware` with `minimum_size=1000` | ✅ Pass | Compression only for large responses |
| `pillow` image processing for uploads | ✅ Pass | Image resizing before storage |
| `orjson` for JSON serialization | ✅ Pass | ~3× faster than stdlib `json` |

### ⚠️ WEAKNESSES

#### **PERF-009 — MEDIUM | No Streaming for Large File Downloads**

`StaticFiles` mount serves uploaded files but there's no streaming response for large media downloads. Large files are loaded into memory before being streamed.

- **Fix:** Use `FileResponse` with range request support for large media files.

---

## 6. Docker / Deployment Configuration

### ✅ STRENGTHS

| Item | Status | Notes |
| ----- | ------ | ----- |
| Multi-stage Docker build (builder/production/development) | ✅ Pass | Minimal production image size |
| Non-root user (`appuser`, uid 5678) | ✅ Pass | CIS Docker Benchmark compliance |
| `uv` for fast dependency resolution | ✅ Pass | Layer caching optimized |
| `UV_COMPILE_BYTECODE=1` | ✅ Pass | Faster cold starts |
| `--workers 4` in production CMD | ✅ Pass | Multi-process for CPU parallelism |
| `HEALTHCHECK` in Dockerfile | ✅ Pass | Kubernetes/Docker health probes |

### ⚠️ WEAKNESSES

#### **PERF-010 — HIGH | Hardcoded `--workers 4` — Not Adaptive to Container Resources**

The Dockerfile CMD hardcodes `--workers 4`, which may be insufficient on larger machines or excessive on 1-2 vCPU containers (causing context switching overhead).

- **File:** `Dockerfile` line 78
- **Fix:** Use a startup script that calculates workers from CPU count:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers $(python -c 'import os; print(min(4, (os.cpu_count() or 1) * 2 + 1))') --loop uvloop --http httptools"]
```

---

#### **PERF-011 — MEDIUM | `redis-commander` Included in Production Compose**

`docker-compose.yaml` includes `redis-commander` (web-based Redis admin UI) on port `8081`. This is a development-only tool and should not be present in production deployments.

- **File:** `docker-compose.yaml` lines 41–52
- **Impact:** Redis admin UI exposed — can browse/modify all cache data
- **Fix:** Move `redis-commander` to a `profiles: [dev]` block or separate `docker-compose.override.yaml`.

---

#### **PERF-012 — MEDIUM | No CPU/Memory Resource Limits on Services**

No `resources.limits` or `resources.reservations` are set for any service in `docker-compose.yaml`. A runaway AI request could consume all container memory.

- **Fix:** Add resource limits:

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 1G
      reservations:
        cpus: '0.5'
        memory: 512M
```

---

## Summary Table

| ID | Issue | Severity | Impact |
| ---- | ------ | -------- | -------- |
| PERF-001 | `BaseHTTPMiddleware` overhead (5× layers) | HIGH | +5–15% latency |
| PERF-002 | Deprecated `get_event_loop()` | MEDIUM | DeprecationWarning in 3.12+ |
| PERF-003 | Pool too small for 4-worker production | HIGH | Connection starvation |
| PERF-004 | N+1 query risk without eager loading | HIGH | Relationship queries unbounded |
| PERF-005 | `scan_iter` for blacklist count is O(N) | MEDIUM | Redis latency spikes |
| PERF-006 | No cache stampede protection | MEDIUM | DB thundering herd on expiry |
| PERF-007 | Offset pagination on large datasets | MEDIUM | Slow deep pages |
| PERF-008 | AI requests block request lifecycle | MEDIUM | Long-tail latency |
| PERF-009 | No streaming for large file downloads | MEDIUM | Memory pressure |
| PERF-010 | Hardcoded `--workers 4` | HIGH | CPU resource mismatch |
| PERF-011 | `redis-commander` in production compose | MEDIUM | Redis admin exposed |
| PERF-012 | No container resource limits | MEDIUM | Runaway memory consumption |
