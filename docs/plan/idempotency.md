# Idempotency Implementation Plan

> **Document Status:** Revised — sections marked `[REVISED]` or `[NEW]` reflect updates to the original plan. Unmarked sections are preserved from the original with minor corrections.

## 1. Objective and Context

The application utilises a robust FastAPI architecture with a global retry policy (`@with_retry`), a comprehensive asynchronous caching system (`CacheManager` backed by Redis), and an integrated database setup using SQLModel/PostgreSQL. While retry mechanisms mitigate transient errors, blindly applying them to `POST` endpoints (like blog creation, user registration) or costly external calls (AI generation) can lead to data duplication, structural errors (like `UniqueConstraintViolation`), and duplicated financial costs.

This document outlines a plan to implement true API idempotency to provide safe retries across the system, ensuring that duplicate requests yield consistent results without duplicate side effects.

> **Scope constraint:** The goal is the simplest correct solution that eliminates the listed failure modes. Complexity is added only when a demonstrated need arises.

## 2. Industry-Standard Approaches Analysis `[REVISED]`

### 2.1 Database Constraints (Unique Keys)

- **Description:** Using database-level unique constraints (e.g., unique indices on `(author_id, slug)` or a dedicated idempotency table).
- **Pros:** Guarantees absolute data consistency; no split-brain issues; survives Redis outages.
- **Cons:** High latency for cross-region setups; does not prevent side-effects like triggering emails or costly AI calls *before* the DB insert occurs; requires a background cleanup job to purge expired rows.

### 2.2 Redis-Based Idempotency Keys (The Stripe Pattern) `[REVISED]`

- **Description:** The client sends an `Idempotency-Key` header with mutation requests (`POST`/`PATCH`/`PUT`). The server performs an atomic `SET key value NX EX <ttl>` in Redis before processing. If the key exists and the request is complete, the cached response is returned verbatim. If processing, the duplicate request receives `409 Conflict`.
- **Stripe specifics this plan adopts:**
  - The key is scoped to the authenticated user, not global.
  - The original request body is fingerprinted (hashed) and stored alongside the key. If the same `Idempotency-Key` is replayed with a *different* body, the server returns `422 Unprocessable Entity` — this is the *conflicting request* guard used by Stripe.
  - The original HTTP status code is stored and replayed verbatim (a `201 Created` replay returns `201`, not `200`).
  - Keys expire after 24 hours; clients must generate a new key for a logically new request after expiry.
- **Pros:** Millisecond latency; protects downstream resources (DB, AI services, email) from duplicate processing; naturally scales horizontally; TTL provides automatic cleanup.
- **Cons:** Requires a reliable distributed cache (already present in this codebase). Adds one Redis round-trip per mutation request.

### 2.3 Specific Recommendation Justified by Codebase Context `[REVISED]`

**Recommendation:** **Redis-Based Idempotency Keys implemented as a pure Starlette `BaseHTTPMiddleware`.**

**Justification:**

The codebase already relies on Redis via `CacheManager`. The idempotency layer uses the *same* Redis connection pool without introducing new infrastructure.

**Critical architectural correction from the original plan:** A FastAPI *dependency* cannot short-circuit a route handler to return a cached response body. Dependencies may raise `HTTPException` (for rejection cases such as missing key or 409 conflict), but they cannot emit a full HTTP response with an arbitrary body in place of the route handler. The only FastAPI-native layers that can intercept the request *before* the route handler and return an early response are:

1. **Starlette `BaseHTTPMiddleware`** — recommended for this use-case; cleanest separation of concerns.
2. A custom `APIRouter` subclass overriding `route` dispatch — significantly more complex, not warranted here.
3. Per-route wrapper decorators — viable but requires touching every route and mixes concerns.

Middleware is the correct layer for a cross-cutting concern like idempotency and aligns with the Single Responsibility Principle.

## 3. Implementation Strategy `[REVISED]`

The implementation follows a phased approach — start with the minimum viable correct solution, then layer in observability and hardening. Do **not** pre-build abstractions not yet needed.

### Phase 1 (MVP): Idempotency Store Interface + Middleware `[REVISED]`

**Step 1a — Define a minimal interface (Dependency Inversion Principle).**

The middleware must not depend directly on `CacheManager`. Define a protocol so the store is swappable (e.g., switch to a DB table if Redis persistence is needed later):

```python
# app/interfaces/idempotency_store.py
from typing import Protocol

class IdempotencyStore(Protocol):
    async def acquire(
        self,
        redis_key: str,
        body_hash: str,
        ttl_seconds: int,
    ) -> dict | None:
        """
        Atomically attempt to claim a key.

        Returns:
            None if the key was newly acquired (caller should proceed).
            A dict with {"status", "status_code", "body", "body_hash"} if
            the key already exists.
        """
        ...

    async def complete(
        self,
        redis_key: str,
        status_code: int,
        body: bytes,
        ttl_seconds: int,
    ) -> None:
        """Store the completed response for future replay."""
        ...

    async def fail(self, redis_key: str, ttl_seconds: int) -> None:
        """
        Release or expire a key that failed so a retry is allowed.
        Use a short TTL (e.g. 60 s) — not the full 24 h — so clients
        can retry after transient server errors.
        """
        ...
```

**Step 1b — Implement `RedisIdempotencyStore`.**

Uses a single atomic Lua script for `acquire` to eliminate the check-then-set race condition that exists in the original plan's two-step `get` → `set` approach:

```python
# app/stores/idempotency.py
# The Lua script guarantees atomicity: check + conditional set in one Redis call.
# This replaces the original plan's non-atomic cache.get() → cache.set() pattern.

ACQUIRE_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
if existing then return existing end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return nil
"""
```

> **Why Lua, not `SET NX`?** `SET key value NX EX ttl` handles the lock, but we also need to read the *existing value* atomically in the same operation when the key already exists. A plain `SETNX` requires a separate `GET`, introducing a TOCTOU gap. The Lua script eliminates this.

**Step 1c — Implement `IdempotencyMiddleware`.**

The middleware is the *only* location where idempotency logic lives. Route handlers and business logic remain completely unaware of idempotency:

```python
# app/middleware/idempotency.py
# Pseudocode — not final implementation; guides the implementer.

class IdempotencyMiddleware(BaseHTTPMiddleware):
    IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}
    KEY_TTL = 86_400        # 24 hours for completed responses
    FAIL_TTL = 60           # 60 s grace for failed/crashed requests

    async def dispatch(self, request: Request, call_next):
        # 1. Only apply to mutation methods with the header present.
        raw_key = request.headers.get("Idempotency-Key")
        if request.method not in self.IDEMPOTENT_METHODS or raw_key is None:
            return await call_next(request)

        # 2. Validate key format (see §4 Security).
        # 3. Resolve user scope; reject unauthenticated requests without key.
        # 4. Hash request body for conflict detection.
        # 5. Atomically acquire key in Redis store.
        #    - If store returns existing record:
        #        a. body_hash mismatch → 422 Unprocessable Entity (conflicting request)
        #        b. status == "processing" → 409 Conflict
        #        c. status == "completed" → replay original status_code + body
        # 6. Call route handler.
        # 7. On success → store.complete(key, status_code, body)
        # 8. On exception → store.fail(key) so the client may retry
```

> **No dependency injection into route handlers.** The idempotency key is resolved, validated, and acted upon entirely within the middleware. Routes are not modified.

### Phase 2: Apply to Target Endpoints

Register the middleware selectively or globally. Because the middleware skips non-mutation methods and requests without the `Idempotency-Key` header, applying it globally carries no risk of regression on read endpoints or endpoints that do not require idempotency.

Target endpoints for mandatory header enforcement (return `400` if header absent):

- `POST /blogs/create`
- All `POST /ai/*` generation endpoints (highest cost per duplicate)
- `POST /auth/register` (raises `UniqueConstraintViolation` without it)

Endpoints where the header is **optional** (idempotency applied if header present, skipped if not):

- `PATCH` and `PUT` endpoints — clients may opt in but it is not enforced.

### Phase 3: Observability and Hardening

Add only after Phase 1 is stable in staging. Do not pre-build. See §6 for details.

> **Over-engineering flag:** The original plan proposed creating an `IdempotencyManager` that extends or wraps `CacheManager`. This is premature abstraction — the idempotency store has a fundamentally different contract from the response cache (atomic acquire/release vs. simple get/set), and coupling them would violate the Single Responsibility Principle. Keep them separate.

## 4. Security Considerations `[REVISED]`

### 4.1 Key Format and Entropy Requirements `[NEW]`

The original plan's check (`len(idempotency_key) < 16`) provides insufficient entropy and no format validation.

**Requirements:**

- **Format:** UUID v4 (`xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`). UUID v4 provides ~122 bits of entropy, which is sufficient to make brute-force collision attacks computationally infeasible.
- **Validation regex:** `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` (case-insensitive). Reject with `400 Bad Request` on mismatch.
- **Length cap:** Reject keys longer than 36 characters to prevent memory exhaustion via crafted long keys.
- **Clients** must generate keys using a cryptographically secure random source (e.g., `uuid.uuid4()` in Python, `crypto.randomUUID()` in browsers). Document this requirement in the API consumer guide.

### 4.2 Key Scoping — Preventing Cross-User Data Leakage `[REVISED]`

The Redis key format must bind the idempotency key to the authenticated user identity:

```text
idemp:{user_uuid}:{idempotency_key}
```

- Even if two users independently generate the same UUID (astronomically unlikely but theoretically possible), their keys do not collide in Redis.
- **Unauthenticated requests** must not use a global namespace. If a route is unauthenticated, either prohibit the `Idempotency-Key` header entirely or scope to a client IP + key fingerprint (documented explicitly per route).
- **Key ownership validation:** Before replaying a cached response, the middleware must verify that the requesting user's `uuid` matches the `user_uuid` encoded in the Redis key. This prevents a user from forging a key that belongs to another user's namespace, even if they somehow learn the value.

### 4.3 Conflicting Request Detection — Replay Attack Guard `[NEW]`

**Problem not addressed in the original plan:** A malicious actor (or client bug) might replay a legitimate `Idempotency-Key` with a *different request body* to hijack the response of the original request or trigger unintended side effects.

**Mitigation:**

1. At `acquire` time, compute `SHA-256(request body)` and store `body_hash` alongside the key record.
2. On subsequent requests with the same key, recompute the hash and compare. If they differ, return `422 Unprocessable Entity` with a clear error body:

   ```json
   {
     "error": "idempotency_conflict",
     "detail": "Idempotency-Key was previously used with a different request body."
   }
   ```

3. Do **not** reveal the original request body or hash value in the error response.

This matches Stripe's behaviour for conflicting idempotent requests.

### 4.4 Sensitive Data in Cache `[NEW]`

**Risk:** Cached responses may contain sensitive fields (tokens, PII, AI-generated content). Redis is a shared cache accessible to all application instances and potentially other services.

**Mitigations:**

- Redis must be deployed with `requirepass` and TLS-in-transit (`tls-port`) enabled. Confirm this in the infrastructure checklist before Phase 1 rollout.
- Do **not** cache responses from authentication endpoints that return tokens (e.g., `POST /auth/login`). Idempotency on auth flows should be handled at the DB constraint level (unique user email), not via response caching.
- Evaluate whether response bodies stored for idempotency should be encrypted at rest in Redis using AES-256. This is a Phase 3 hardening item — not required for MVP, but must be assessed before production rollout of any endpoint that returns session tokens or PII.
- Set Redis `maxmemory-policy` to `allkeys-lru` or `volatile-lru` so idempotency keys are evicted under memory pressure before non-volatile keys.

### 4.5 Race Condition Prevention `[REVISED]`

The original plan's two-step `cache.get()` → `cache.set()` has a TOCTOU (time-of-check-time-of-use) race condition: two concurrent duplicate requests can both read "not found" and both proceed to process.

**Correct approach:** Use the atomic Lua script described in §3 Phase 1b. This guarantees that only one request ever transitions a key from "absent" to "processing". All concurrent duplicates either see `processing` (→ `409`) or `completed` (→ replay).

### 4.6 Rate Limiting on Key Creation `[NEW]`

Without limits, a client could flood the server with unique idempotency keys, one per request, effectively bypassing any deduplication benefit and consuming Redis memory. Apply a per-user rate limit on the rate of *new* idempotency key creation (distinct from the general API rate limit). Recommended: no more than 1,000 unique idempotency keys created per user per hour. Enforce via the existing rate-limiting middleware.

## 5. Scalability Analysis `[REVISED]`

### 5.1 Horizontal Scaling

Redis is single-threaded and handles atomic operations correctly per-node. The `idemp:{user_uuid}:{key}` key format maps naturally to a specific Redis Cluster shard. If Redis Cluster is used, apply hash tagging to co-locate related keys: `idemp:{user_uuid}:{key}` (the `{user_uuid}` portion acts as the hash tag automatically with curly-brace notation: `idemp:{{user_uuid}}:{key}`). This ensures all idempotency keys for a given user land on the same shard, preserving atomicity without cross-slot Lua script execution errors.

> **Hard-coded assumption to avoid:** Do not store idempotency state in application memory (e.g., an in-process `dict`). This was not proposed in the original plan but is called out here because in-memory storage is a common temptation for "quick" implementations that silently breaks under horizontal scaling — each instance would have its own state.

### 5.2 Storage Implications

Idempotency keys are transient by design (24-hour TTL). Storage estimate:

- Assumes 100,000 `POST` requests/day.
- Per-key record: `~100 bytes` (metadata) + response body (variable). Estimate `~1 KB` average for JSON responses, `~5–50 KB` for AI-generated content responses.
- **AI endpoint responses must be size-capped before caching** (e.g., 64 KB hard limit). Large AI responses that exceed the cap should be stored by reference (e.g., S3 object key stored in Redis, body retrieved on replay). Flag this as a Phase 2 decision — do not pre-build it in Phase 1.
- Total estimate for non-AI endpoints: `~100 MB/day` peak Redis usage for idempotency keys. Negligible on current infrastructure.

### 5.3 Graceful Degradation `[NEW]`

**The original plan does not address what happens when the idempotency store is unavailable.**

This is a critical gap: if Redis is down and the middleware blocks all mutation requests, the outage is total.

**Required behaviour:**

| Redis State | Middleware Behaviour |
| --- | --- |
| Healthy | Full idempotency enforcement. |
| Degraded / timeout | **Fail open**: log a `WARNING`, emit a metric, and allow the request through without idempotency protection. Return a `Warning` response header: `Idempotency-Store-Unavailable: true`. |
| Down (connection refused) | Same as degraded. |

**Rationale:** Idempotency is a reliability enhancement, not a security boundary. Failing closed (blocking all requests) during a Redis outage is worse than failing open (accepting duplicate risk for a short period). The trade-off must be explicitly documented per endpoint — if an endpoint has zero tolerance for duplicates (e.g., financial transactions), add a DB-level unique constraint as a secondary guard.

### 5.4 Stuck `processing` Key Recovery `[NEW]`

**Problem not addressed in the original plan:** If the server crashes, is killed (SIGKILL), or loses the Redis connection *after* marking a key `processing` but *before* calling `store.complete()`, the key remains stuck in `processing` state for the full 24-hour TTL. All subsequent retries receive `409 Conflict` indefinitely — the client can never recover without manual intervention.

**Solution:**

1. **Short processing TTL:** Mark the key `processing` with a short TTL, e.g., 30 seconds (configurable via `IDEMPOTENCY_PROCESSING_TTL_SECONDS`). If the request does not complete within that window (abnormal), the key naturally expires and the client can retry safely.
2. **Extend on progress:** If a route is known to take longer than 30 seconds (e.g., long-running AI generation), the middleware extends the `processing` TTL periodically via a background task.
3. **On success:** Call `store.complete()` immediately, which overwrites the short-TTL record with the full 24-hour completed record.
4. **On handled exception:** Call `store.fail()` with a 60-second TTL (configurable), allowing the client to retry after a brief back-off.

This makes key lifecycle deterministic and eliminates permanently stuck states.

## 6. Maintenance Considerations `[REVISED]`

### 6.1 Observability

The original plan mentions monitoring but lacks specifics on what to measure and what thresholds warrant an alert.

**Structured log fields** (inject into every idempotency middleware execution):

```python
# Fields to include in every structured log record produced by the middleware
{
    "idempotency_key": "<uuid>",       # the raw client key (not the Redis key)
    "idempotency_user": "<user_uuid>", # scoped user
    "idempotency_result": "miss" | "hit_completed" | "hit_processing" | "conflict" | "store_unavailable",
    "idempotency_replay_status": 201,  # only on hit_completed; original status code replayed
    "request_body_hash": "<sha256>",   # truncated to first 8 chars in logs
}
```

**Prometheus metrics to add** (Phase 2, not Phase 1):

| Metric | Type | Alert Threshold |
| --- | --- | --- |
| `idempotency_hits_total` | Counter (label: `result`) | — |
| `idempotency_store_errors_total` | Counter | Alert if > 5/min (Redis issues) |
| `idempotency_duplicate_rate` | Gauge (hits / total requests) | Alert if > 20% sustained (retry storm) |
| `idempotency_conflict_total` | Counter | Alert if > 0 (indicates client bug or attack) |

**Loguru context binding:** The middleware must bind `idempotency_key` and `idempotency_result` into the Loguru context var at the start of each request so all downstream log records from that request are automatically correlated.

### 6.2 Debugging

- The `Idempotency-Key` value must appear in every log line for the duration of the request (via context binding, not repeated arguments).
- On `hit_completed` replays, log at `DEBUG` level only (not `INFO`) to avoid log noise from healthy client retries.
- On `conflict` or `hit_processing`, log at `WARNING` to aid debugging of client-side bugs.
- On `store_unavailable`, log at `ERROR` with the underlying exception for infrastructure alerting.

### 6.3 Future Extensibility

The `IdempotencyStore` protocol defined in §3 allows swapping the backend without touching the middleware:

- **Redis → PostgreSQL JSONB:** Implement `PostgresIdempotencyStore` conforming to the same protocol. Warranted only if Redis persistence requirements change — do not pre-build.
- **Encryption at rest:** Add an optional `encrypt_body: bool` flag to `RedisIdempotencyStore` — encrypted with a key from `settings`. Phase 3 item.
- **Per-endpoint TTL override:** Allow routes to declare a custom TTL (e.g., via a route attribute or header). Warranted only if operational evidence shows 24 hours is wrong for specific endpoints.

> **Tight-coupling risk:** Do not reference `IdempotencyMiddleware` directly inside any route, service, or manager. Routes must remain idempotency-unaware. If a future developer adds `request.state.idempotency_key` checks inside a route handler, that is a violation to flag in code review.

## 7. SOLID Design Principles Review `[NEW]`

| Principle | Assessment | Required Action |
| --- | --- | --- |
| **S** — Single Responsibility | The original `check_idempotency` function performs validation, cache lookup, state mutation, and partial response construction. Violation. | Split into: `IdempotencyKeyValidator` (format), `IdempotencyStore` (persistence), `IdempotencyMiddleware` (orchestration). |
| **O** — Open/Closed | The original plan hard-codes Redis calls. Closed to extension without modification. | The `IdempotencyStore` protocol makes the middleware open to new store backends without modification. |
| **L** — Liskov Substitution | Any concrete `IdempotencyStore` implementation must be substitutable without the middleware changing behaviour. | Enforced by defining the protocol with precise return type contracts (see §3). |
| **I** — Interface Segregation | `CacheManager` has methods for response caching, TTL management, etc. that are unrelated to idempotency. | Do not inherit from or extend `CacheManager`. Use `IdempotencyStore` as a focused interface. |
| **D** — Dependency Inversion | The middleware must receive a concrete `IdempotencyStore` instance via constructor injection, not instantiate it directly. | Register `RedisIdempotencyStore` in `app.state` at startup; pass it to `IdempotencyMiddleware` constructor. |

**Testability requirement:** The middleware must be unit-testable with a mock/fake `IdempotencyStore` (an in-memory `dict`-backed implementation). Integration tests must use a real Redis instance (via `testcontainers` or a Docker fixture). Both test types are required before Phase 1 is considered complete.

## 8. Trade-off Decisions `[REVISED]`

| Decision | Rationale | Alternative Considered |
| --- | --- | --- |
| **Redis vs Database storage** | Redis provides lower latency and native TTL. The app already relies on Redis, avoiding new infrastructure. | Postgres `idempotency_keys` table. Viable as a secondary guard for zero-tolerance endpoints; rejected as primary store due to write overhead and required cleanup jobs. |
| **Middleware vs Dependency** | Middleware is the only FastAPI-native layer that can short-circuit a route handler and return a full cached response. Dependencies cannot. | FastAPI dependency. Rejected — cannot return a response body, only raise exceptions. |
| **Atomic Lua script vs `SET NX`** | Lua eliminates the TOCTOU race in the original plan's two-step get → set. | `SET NX` + separate `GET`. Rejected — has a race window under high concurrency. |
| **Fail open on store unavailability** | Idempotency is a reliability guard, not a security gate. Failing closed during a Redis outage causes total mutation downtime, which is worse than brief duplicate risk. | Fail closed (reject all mutation requests if Redis unavailable). Rejected for endpoints without financial consequences. Endpoints with zero-tolerance for duplicates must also have a DB unique constraint. |
| **Short `processing` TTL (30s) + extension** | Eliminates permanently stuck keys after server crashes. | Full 24-hour processing TTL. Rejected — a crashed instance leaves keys locked for 24 hours with no client recovery path. |
| **UUID v4 format enforcement** | 122-bit entropy makes brute-force key guessing computationally infeasible. Strict format rejects injection attempts and caps key length. | Arbitrary string ≥ 16 chars (original plan). Rejected — insufficient entropy and no injection protection. |
| **User-scoped keys** | Prevents cross-user response leakage even if two clients happen to generate the same UUID. | Global keys. Rejected — severe security implications. |
| **Request body hash for conflict detection** | Matches Stripe's behaviour; guards against key re-use attacks and client bugs. | No conflict detection (original plan). Rejected — leaves the system vulnerable to undetected body-mismatch replays. |

## 9. Summary of Action Items `[REVISED]`

**Phase 1 — MVP (implement in this order):**

1. Define `IdempotencyStore` protocol in `app/interfaces/idempotency_store.py`.
2. Implement `RedisIdempotencyStore` with atomic Lua `acquire`, `complete`, and `fail` methods in `app/stores/idempotency.py`.
3. Register `RedisIdempotencyStore` instance in `app.state` at application startup (`app/main.py`).
4. Implement `IdempotencyMiddleware` in `app/middleware/idempotency.py` with: UUID v4 key validation, user-scoped Redis key, body hash fingerprinting, graceful degradation on store errors, and short processing TTL.
5. Register the middleware in `app/main.py`.
6. Add a per-endpoint `requires_idempotency_key: bool` flag (via route metadata or a dedicated `APIRoute` subclass) to enforce the mandatory header on: `POST /blogs/create`, all `POST /ai/*`, `POST /auth/register`.
7. Write unit tests (mock store) and integration tests (real Redis) covering: first request succeeds, replay returns cached response with original status code, concurrent duplicate returns `409`, body mismatch returns `422`, missing key returns `400` on required endpoints, store unavailable fails open.

**Phase 2 — Observability (after Phase 1 is stable in staging):**

1. Add Prometheus metrics to `IdempotencyMiddleware`.
2. Bind `idempotency_key` and `idempotency_result` to Loguru context per request.
3. Configure alerting thresholds (see §6.1).

**Phase 3 — Hardening (after Phase 2, based on production evidence):**

1. Evaluate response encryption at rest in Redis for endpoints returning PII or tokens.
2. Implement per-endpoint TTL overrides if 24 hours proves incorrect for specific routes.
3. Assess AI endpoint response size capping and S3-reference storage if responses exceed 64 KB.
4. Update `docs/prompts/idempotency.md` to guide developers on adding the `Idempotency-Key` header requirement to new routes.
