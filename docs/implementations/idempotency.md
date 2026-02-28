# Idempotency — Implementation Guide

> **Status:** Implemented (Phase 1 complete)
> **Last updated:** 2026-02-28

---

## 1. What is Idempotency and Why Does It Matter?

An HTTP operation is **idempotent** when repeating it any number of times produces the same result as executing it once. `GET`, `PUT`, and `DELETE` are naturally idempotent by the HTTP specification. `POST` and `PATCH` are not — a naive retry of `POST /blogs/create` would create a duplicate blog post.

Network failures, client timeouts, and mobile reconnects all cause clients to retry requests. Without idempotency protection, these retries silently corrupt data. This implementation follows the **Stripe pattern**: the client generates a UUID v4 `Idempotency-Key` header, and the server guarantees that any number of identical retries produce exactly one side-effect and return the original response.

---

## 2. Architecture Overview

```text
Client
  │
  │  POST /blogs/create
  │  Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
  ▼
┌─────────────────────────────────────────────────────────┐
│  IdempotencyMiddleware  (BaseHTTPMiddleware)             │
│                                                         │
│  1. Skip non-mutation methods (GET, HEAD, DELETE)       │
│  2. Enforce header on required paths (→ 400 if absent)  │
│  3. Validate UUID v4 format (→ 400 if invalid)          │
│  4. Derive user-scoped Redis key                        │
│  5. Atomic acquire via Lua script                       │
│     ├─ Fresh key  → proceed to route handler            │
│     ├─ processing → 409 Conflict                        │
│     ├─ completed + same body → replay original response │
│     └─ completed + diff body → 422 Conflict             │
│  6. Store completed response (status + body + hash)     │
│  7. On error → fail-open (request proceeds)             │
└─────────────────────────────────────────────────────────┘
  │
  ▼
Route Handler (FastAPI)
  │
  ▼
RedisIdempotencyStore
```

**Why `BaseHTTPMiddleware` and not a FastAPI dependency?**
A FastAPI dependency can only raise `HTTPException`. It cannot return a full `Response` object to short-circuit the route handler. Only middleware can intercept the request before the route handler runs and return a cached response body verbatim.

---

## 3. File Structure

```text
app/
├── interfaces/
│   ├── __init__.py
│   └── idempotency_store.py   # IdempotencyStore Protocol (SOLID-D)
├── stores/
│   ├── __init__.py
│   └── idempotency.py         # RedisIdempotencyStore (concrete impl)
└── middleware/
    ├── idempotency.py         # IdempotencyMiddleware
    └── __init__.py            # exports IdempotencyMiddleware

tests/
└── middleware/
    └── test_idempotency_middleware.py  # 11 unit tests (mock store)
```

---

## 4. Key Design Decisions

### 4.1 User-Scoped Redis Keys

Redis keys follow the schema: `idemp:{scope}:{idempotency_key}`

- `scope` = authenticated user's UUID (extracted from JWT Bearer token)
- Fallback for unauthenticated routes (e.g. `/auth/register`): client IP address

This prevents cross-user key collisions. User A cannot replay User B's response by guessing the key.

### 4.2 Atomic Lua Script (No TOCTOU Race)

A naive `GET` → `SET NX` two-step has a race window: two concurrent requests can both see the key as absent and both proceed. The `acquire` operation uses a single Lua script executed atomically by Redis:

```lua
local existing = redis.call('GET', KEYS[1])
if existing then
    return existing
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', tonumber(ARGV[2]))
return nil
```

`nil` return = key freshly acquired (caller proceeds). Non-nil = existing record (caller inspects status).

### 4.3 Request Body Fingerprinting

The middleware computes `SHA-256(request_body)` and stores it alongside the key. On replay, if the body hash differs, the server returns `422 Unprocessable Entity` with `error: "idempotency_conflict"`. This prevents a client from accidentally (or maliciously) reusing a key for a different operation.

### 4.4 Deterministic Key Lifecycle

| State        | TTL      | Meaning                                              |
|--------------|----------|------------------------------------------------------|
| `processing` | 30 s     | Request in flight. Prevents concurrent duplicates.   |
| `completed`  | 24 h     | Response cached. Replayed verbatim on retry.         |
| `failed`     | 60 s     | Handler errored. Client may retry after 60 s.        |

The 30-second processing TTL prevents permanently stuck keys if the server crashes mid-request.

### 4.5 Fail-Open Strategy

If Redis is unavailable (network partition, restart), the middleware logs a warning and **allows the request to proceed** without idempotency protection. A `Idempotency-Store-Unavailable: true` response header signals the degraded state to the client. This prioritises API availability over strict idempotency guarantees during outages.

---

## 5. Required Endpoints

The following endpoints **require** the `Idempotency-Key` header. Requests without it receive `400 Bad Request`:

| Method | Path                  | Reason                                      |
|--------|-----------------------|---------------------------------------------|
| POST   | `/blogs/create`       | Creates a blog post — duplicate = data loss |
| POST   | `/auth/register`      | Creates a user account — duplicate = error  |
| POST   | `/ai/chat`            | Expensive AI call — duplicate = cost        |
| POST   | `/ai/email-inquiry/`  | Sends an email — duplicate = spam           |
| POST   | `/ai/itinerary-md`    | Expensive AI call — duplicate = cost        |
| POST   | `/ai/itinerary-txt`   | Expensive AI call — duplicate = cost        |

---

## 6. Client Usage Guide

### Generating a Key

Always generate a fresh UUID v4 **per logical operation**, not per retry:

```python
import uuid
idempotency_key = str(uuid.uuid4())  # e.g. "550e8400-e29b-41d4-a716-446655440000"
```

### Making a Request

```http
POST /blogs/create HTTP/1.1
Authorization: Bearer <access_token>
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
Content-Type: application/json

{"title": "My Bali Trip", "content": "..."}
```

### Retry Logic

```python
import httpx, uuid, time

key = str(uuid.uuid4())  # Generate ONCE before the retry loop
for attempt in range(3):
    resp = httpx.post(
        "/blogs/create",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    if resp.status_code in (200, 201):
        break  # Success (or replay)
    if resp.status_code == 409:
        time.sleep(2 ** attempt)  # Exponential back-off for in-progress
    elif resp.status_code == 422:
        raise ValueError("Key reused with different body — generate a new key")
    else:
        raise RuntimeError(f"Unexpected: {resp.status_code}")
```

### Response Headers

| Header                          | Meaning                                      |
|---------------------------------|----------------------------------------------|
| `Idempotent-Replayed: true`     | Response was replayed from cache             |
| `Idempotency-Store-Unavailable` | Store was down; idempotency not guaranteed   |

---

## 7. Error Reference

| Status | `error` field              | Cause                                              |
|--------|----------------------------|----------------------------------------------------|
| 400    | `missing_idempotency_key`  | Header absent on a required endpoint               |
| 400    | `invalid_idempotency_key`  | Header present but not a valid UUID v4             |
| 409    | `request_in_progress`      | Same key is currently being processed              |
| 409    | `request_failed`           | Previous request with this key failed; retry later |
| 422    | `idempotency_conflict`     | Same key reused with a different request body      |

---

## 8. Initialisation Flow

The `RedisIdempotencyStore` is initialised during the application lifespan in `_blacklist_and_tracker_init` (`app/middleware/middleware.py`) and stored in `app.state.idempotency_store`. The middleware lazily resolves the store from `request.app.state` on the first request, so it can be registered in `main.py` before the lifespan runs.

```python
# app/main.py
app.add_middleware(IdempotencyMiddleware)  # store=None → resolved from app.state

# app/middleware/middleware.py (_blacklist_and_tracker_init)
app.state.idempotency_store = RedisIdempotencyStore(redis_client.client)
```

---

## 9. Testing

Unit tests live in `tests/middleware/test_idempotency_middleware.py`. They use a mock `IdempotencyStore` — no Redis required.

```bash
# Run idempotency tests only
.venv/bin/pytest tests/middleware/test_idempotency_middleware.py -v --no-cov

# Expected: 11 passed
```

### Test Coverage

| Test | Scenario |
| ---- | -------- |
| `test_first_request_proceeds_and_stores_response` | Fresh key → route runs, response stored |
| `test_replay_completed_response` | Completed key + same body → 201 replay |
| `test_concurrent_duplicate_returns_409` | Processing key → 409 |
| `test_body_mismatch_returns_422` | Completed key + different body → 422 |
| `test_missing_key_on_required_path_returns_400` | No header on required path → 400 |
| `test_missing_key_on_optional_path_passes_through` | No header on optional path → pass through |
| `test_invalid_uuid_format_returns_400` | Non-UUID key → 400 |
| `test_store_unavailable_fails_open` | Store raises → request proceeds, warning header |
| `test_get_request_skips_idempotency` | GET → middleware skipped entirely |
| `test_store_resolved_from_app_state` | `store=None` → resolved from `app.state` |
| `test_no_store_in_app_state_fails_open` | `store=None`, no state → fail-open |

---

## 10. Extending the Implementation

### Adding a New Required Endpoint

Update `IdempotencyMiddleware.REQUIRED_PATHS` in `app/middleware/idempotency.py`:

```python
REQUIRED_PATHS: ClassVar[frozenset[tuple[str, str]]] = frozenset({
    ("POST", "/blogs/create"),
    ("POST", "/your/new/endpoint"),  # ← add here
    ...
})
```

Then add `openapi_extra` to the route decorator for OpenAPI documentation (see existing routes for the pattern).

### Swapping the Store Backend

Implement the `IdempotencyStore` protocol from `app/interfaces/idempotency_store.py` with any backend (PostgreSQL, DynamoDB, in-memory). Inject it via `app.state.idempotency_store` in the lifespan. No middleware changes required.
