# Remediation Roadmap — BaliBlissed Backend
>
> **Date:** 2026-03-03 | **Priority:** Sprint-aligned action plan

---

## Prioritization Matrix

> Issues sorted by: **Severity → Exploitability → Implementation Effort**

| Sprint | Priority | Effort | Issues |
| ----- | -------- | ------ | ------ |  
| **Sprint 1** (This week) | HIGH Security + Quick Wins | Small–Medium | SEC-003, SEC-005, SEC-010, SEC-013 |
| **Sprint 2** | HIGH Performance | Medium | PERF-001, PERF-003, PERF-010 |
| **Sprint 3** | MEDIUM Security + Performance | Medium | SEC-001, SEC-007, SEC-008, SEC-009, PERF-004, PERF-005 |
| **Sprint 4** | Strategic Architecture | Large | SEC-002, PERF-007, PERF-008 |
| **Backlog** | LOW + Strategic | Small–Large | SEC-011, SEC-012, PERF-011, PERF-012 |

---

## Sprint 1: Must Fix Before Next Deployment

### REM-01 — Add Missing Sentinel to `SECRET_KEY` Validator

**Addresses:** SEC-003 | **Effort:** 30 minutes

```python
# app/configs/settings.py — Fix line 265
@field_validator("SECRET_KEY")
@classmethod
def validate_secret_key(cls, v: str, info: ValidationInfo) -> str:
    """Ensure SECRET_KEY is set and secure."""
    # ADD: Actual default value used in class (line 111)
    forbidden = {
        "your-secret-key-change-this-in-production",
        "dev-only-insecure-key-replace-in-prod"
    }
    if not v or v in forbidden:
        env = info.data.get("ENVIRONMENT", "development")
        if env == "production":
            msg = "SECRET_KEY must be set to a secure value in production!"
            raise ValueError(msg)
    # ... rest of validation
```

---

### REM-02 — Restrict Public Health / Metrics Exposure

**Addresses:** SEC-005 | **Effort:** 30 minutes

```python
# app/routes/health.py — protect full health and legacy metrics

@router.get("/health")
async def health_check(
    user: AdminUserDep,   # ADD: admin-only gate
    email_client: EmailDep,
    health_checker: HealthCheckerDep,
) -> ORJSONResponse:
    ...

@router.get("/metrics/legacy")
async def legacy_metrics(
    _admin: AdminUserDep,   # ADD: admin-only gate
    ...
```

> **Note:** `/health/live` and `/health/ready` remain public for Kubernetes probes. This keeps the validated nuance intact: not every health endpoint must be gated, but the broader system-state views should not remain broadly public.

---

### REM-03 — Add User ID to Rate Limit Identifier

**Addresses:** SEC-010 | **Effort:** 1 hour

```python
# app/managers/rate_limiter.py
from fastapi import Request
from slowapi.util import get_remote_address

def get_identifier(request: Request) -> str:
    """Composite key: verified user > API key > client IP."""
    # 1. Prefer authenticated user ID (un-spoofable)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"

    # 2. Existing API key check (unverified)
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return f"apikey:{api_key}"

    # 3. Fallback to IP
    return f"ip:{get_remote_address(request)}"
```

Also ensure `request.state.user_id` is populated by `get_current_user` dependency for all authenticated routes.

---

### REM-04 — Strip PII from Access Logs

**Addresses:** SEC-013 | **Effort:** 1 hour

```python
# app/middleware/middleware.py — LoggingMiddleware.dispatch
logger.info(
    "Request started",
    path=request.url.path,
    method=request.method,
    client_ip=_mask_ip(client_ip),  # Mask last octet for GDPR
)
```

```python
# app/services/email_inquiry.py — avoid logging caller-provided name verbatim
logger.info(
    "Email inquiry submitted",
    client_ip=_mask_ip(client_ip),
    name_present=bool(name),
)
```

---

### REM-05 — Standardize on One JWT Library

**Addresses:** SEC-001 | **Effort:** 1 hour

Keep the currently used library or migrate deliberately, but remove the duplicate dependency so the runtime and dependency set match.

```diff
# pyproject.toml
  dependencies = [
-   "PyJWT>=2.9.0",
    "python-jose[cryptography]>=3.5.0",
```

**Verification:**

1. Confirm the intended JWT library for long-term use.
2. Remove the unused duplicate dependency.
3. If a later migration is desired, handle that as a separate change set.

---

## Sprint 2: Fix Within This Sprint

### REM-06 — Tune Connection Pool for Production

**Addresses:** PERF-003 | **Effort:** 1 hour

```python
# app/configs/settings.py
POOL_SIZE: int = 10      # was 5
MAX_OVERFLOW: int = 5    # was 10
POOL_TIMEOUT: int = 10   # was 30 (fail faster, don't hold request open)
POOL_RECYCLE: int = 1800 # was 3600 (30 min recycle for cloud environments)
```

For a 4-worker deployment: max concurrent connections = 4 × 15 = 60 (within default PostgreSQL `max_connections=100`).

---

### REM-07 — Adaptive Worker Count in Docker CMD

**Addresses:** PERF-010 | **Effort:** 2 hours

Create a startup wrapper script:

```dockerfile
# scripts/start.sh
#!/bin/sh
WORKERS=${UVICORN_WORKERS:-$(python -c "import os; print(min(4, (os.cpu_count() or 1) * 2 + 1))")}
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "$WORKERS" \
    --loop uvloop \
    --http httptools \
    --log-level info
```

```dockerfile
# Dockerfile (production stage)
COPY scripts/start.sh ./scripts/start.sh
RUN chmod +x ./scripts/start.sh
CMD ["./scripts/start.sh"]
```

---

### REM-08 — Migrate Pure ASGI Middleware for Security Headers

**Addresses:** PERF-001 (partial) | **Effort:** 3 hours

Convert `SecurityHeadersMiddleware` to pure ASGI first (highest frequency, safest to test):

```python
# app/middleware/security_headers.py
from starlette.types import ASGIApp, Receive, Scope, Send, Message
from starlette.datastructures import MutableHeaders

class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Content-Type-Options", "nosniff")
                headers.append("X-Frame-Options", "DENY")
                headers.append("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
                headers.append("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.append("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            await send(message)

        await self.app(scope, receive, send_with_headers)
```

---

## Sprint 3: Fix in Next Cycle

### REM-09 — Restrict CORS `allow_headers`

**Addresses:** SEC-007 | **Effort:** 30 minutes

```python
# app/middleware/middleware.py — configure_cors()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "Idempotency-Key",
        "X-Client-Timezone",
        "Accept",
        "Accept-Language",
    ],
    expose_headers=["X-Request-ID"],
)
```

---

### REM-10 — Add CSP and Permissions-Policy Headers

**Addresses:** SEC-008 | **Effort:** 1 hour

```python
# app/middleware/security_headers.py (or existing SecurityHeadersMiddleware)
response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
response.headers["X-DNS-Prefetch-Control"] = "off"
```

---

### REM-11 — Validate `X-Client-Timezone` Header

**Addresses:** SEC-009 | **Effort:** 1 hour

```python
# app/middleware/timezone.py
import zoneinfo

_VALID_TIMEZONES = zoneinfo.available_timezones()

class TimezoneMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw_tz = request.headers.get("X-Client-Timezone", "UTC")
        request.state.user_timezone = raw_tz if raw_tz in _VALID_TIMEZONES else "UTC"
        return await call_next(request)
```

---

### REM-12 — Add Eager Loading Convention to `BaseRepository`

**Addresses:** PERF-004 | **Effort:** 2 hours

```python
# app/repositories/base.py
from sqlalchemy.orm import selectinload, RelationshipProperty
from sqlalchemy import inspect as sa_inspect

async def get_many(
    self,
    *,
    load_options: list | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[ModelT]:
    stmt = select(self.model)
    if load_options:
        for opt in load_options:
            stmt = stmt.options(opt)
    if offset:
        stmt = stmt.offset(offset)
    if limit:
        stmt = stmt.limit(limit)
    result = await self.session.execute(stmt)
    return list(result.scalars().all())
```

---

### REM-13 — Replace `scan_iter` Blacklist Count with Constant-Time Counter

**Addresses:** PERF-005 | **Effort:** 1 hour

```python
# app/managers/token_blacklist.py
BLACKLIST_COUNT_KEY = "token_blacklist:count"

async def blacklist_token(...):
    ...
    pipe = self.redis.pipeline()
    pipe.setex(token_key, ttl_seconds, value)
    pipe.incr(BLACKLIST_COUNT_KEY)
    await pipe.execute()

async def get_blacklist_count(self) -> int:
    raw = await self.redis.get(BLACKLIST_COUNT_KEY)
    return int(raw or 0)
```

---

## Sprint 4: Architecture Improvements

### REM-14 — JWT Algorithm Migration to RS256

**Addresses:** SEC-002 | **Effort:** 1 day (with key generation and service coordination)

```python
# app/configs/settings.py
ALGORITHM: str = "RS256"
JWT_PRIVATE_KEY_PATH: Path = Path("secrets/jwt_private.pem")
JWT_PUBLIC_KEY_PATH: Path = Path("secrets/jwt_public.pem")

@property
def jwt_private_key(self) -> str:
    return self.JWT_PRIVATE_KEY_PATH.read_text()

@property
def jwt_public_key(self) -> str:
    return self.JWT_PUBLIC_KEY_PATH.read_text()
```

Key generation:

```bash
openssl genrsa -out secrets/jwt_private.pem 2048
openssl rsa -in secrets/jwt_private.pem -pubout -out secrets/jwt_public.pem
```

---

### REM-15 — AI Operations via Background Task Queue

**Addresses:** PERF-008 | **Effort:** 3 days

Integrate `arq` (async Redis Queue — lightweight alternative to Celery):

```python
# app/workers/ai_worker.py
from arq import create_pool
from arq.connections import RedisSettings

async def generate_itinerary_task(ctx, payload: dict) -> dict:
    ai_client = ctx["ai_client"]
    return await ai_client.generate_itinerary(**payload)

class WorkerSettings:
    functions = [generate_itinerary_task]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```

```python
# app/routes/ai.py
@router.post("/ai/itinerary", status_code=202)
async def create_itinerary(body: ItineraryRequest, request: Request) -> dict:
    pool = request.app.state.task_pool
    job = await pool.enqueue_job("generate_itinerary_task", body.model_dump())
    return {"job_id": job.job_id, "status": "queued"}

@router.get("/ai/itinerary/{job_id}")
async def get_itinerary_result(job_id: str, request: Request) -> dict:
    pool = request.app.state.task_pool
    job = await Job(job_id=job_id, redis=pool).result(timeout=1)
    return {"status": job.status, "result": job.result}
```

---

### REM-16 — Introduce Secret Rotation Strategy

**Addresses:** SEC-012 | **Effort:** 1–2 days

Move from static environment-file secrets toward a runtime-injected secret source so key rotation is operationally possible without editing the repository-managed `.env` workflow.

```python
# app/configs/settings.py
SECRET_KEY: str = Field(...)

# deployment/runtime
# export SECRET_KEY from a secret manager or orchestration secret store
```

At minimum, document rotation ownership, rotation cadence, and how applications reload updated values.

---

## Backlog Items

### REM-17 — Move `redis-commander` to Dev Profile

**Addresses:** PERF-011 | **Effort:** 15 minutes

```yaml
# docker-compose.yaml
redis-commander:
  ...
  profiles:
    - dev   # Only started with: docker compose --profile dev up
```

---

### REM-18 — Add Container Resource Limits

**Addresses:** PERF-012 | **Effort:** 30 minutes

```yaml
# docker-compose.prod.yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 1G
      reservations:
        cpus: '0.5'
        memory: 256M
```

---

### REM-19 — Keep `rich.print` Out of Production Config Paths

**Addresses:** SEC-011 | **Effort:** 15 minutes

Remove the `rich.print` import from configuration/security modules unless it is strictly required for local debugging.

---

## Architecture Recommendations

### 1. Transition to Pure ASGI Middleware (All Middlewares)

Convert all 5 `BaseHTTPMiddleware` subclasses to pure ASGI callables to eliminate 5× middleware overhead. Timeline: 1 sprint per middleware, starting with the highest-frequency ones.

### 2. Introduce a Secrets Manager Integration

**Addresses:** SEC-012

Current: `secrets/.env` (git-crypt). Recommended: AWS Secrets Manager or HashiCorp Vault with dynamic secret injection at startup. This enables rotation without redeployment.

### 3. API Versioning Strategy

Currently no API versioning. Implement URL path versioning (`/v1/`) before the first breaking change:

```python
# app/routes/__init__.py
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth_router)
v1_router.include_router(user_router)
# ...
```

### 4. Cursor-Based Pagination for Production Dataset Growth

**Addresses:** PERF-007

Implement before the database grows beyond 50K rows in any primary table.

### 5. Sentry Integration

`SENTRY_DSN` is configured but no Sentry initialization is present in `main.py`. Add:

```python
import sentry_sdk
if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE)
```

---

## Effort Summary

| Sprint | Issues Fixed | Total Effort | Priority |
| ----- | ------ | ------ | ------ |
| Sprint 1 | REM-01 to REM-05 | ~6 hours | 🚨 HIGH |
| Sprint 2 | REM-06 to REM-08 | ~6 hours | ⚠️ HIGH |
| Sprint 3 | REM-09 to REM-13 | ~8 hours | 🔔 MEDIUM |
| Sprint 4 | REM-14 to REM-16 | ~5 days | 🔵 STRATEGIC |
| Backlog | REM-17 to REM-19 | ~1 hour | ℹ️ LOW |
