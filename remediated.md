# Confirmed completed audit items

- [x] **PERF-002 — Replace deprecated `get_event_loop()` usage**
  - Confirmed in `app/middleware/middleware.py` via `get_running_loop()`.

- [x] **PERF-003 — Tune DB pool defaults for production**
  - Confirmed in `app/configs/settings.py`: `POOL_SIZE=10`, `MAX_OVERFLOW=5`, `POOL_TIMEOUT=10`, `POOL_RECYCLE=1800`.

- [x] **PERF-004 — Add repository eager-loading convention support**
  - Confirmed in `app/repositories/base.py` via `get_many(..., load_options=None, limit=None, offset=None)` and option application through `statement.options(...)`.

- [x] **PERF-005 — Remove O(N) blacklist counting via `scan_iter`**
  - Confirmed in `app/managers/token_blacklist.py` by replacing scan-based counting with a Redis sorted-set index using `zadd`, `zrem`, `zremrangebyscore`, and `zcard`.

- [x] **PERF-010 — Make production worker count adaptive**
  - Confirmed by `Dockerfile` using `scripts/start-prod.sh`, which derives worker count from CPU count and DB connection budget unless `WEB_CONCURRENCY` is explicitly set.

- [x] **PERF-011 — Isolate `redis-commander` to dev-only startup**
  - Confirmed in `docker-compose.yaml` with `profiles: [dev]` on `redis-commander`.

- [x] **PERF-012 — Add container CPU/memory resource limits**
  - Confirmed in both `docker-compose.yaml` and `docker-compose.prod.yaml` with backend `deploy.resources` limits and reservations.

- [x] **PERF-001 — Convert the remaining low-risk custom middleware layers away from `BaseHTTPMiddleware`**
  - Confirmed pure-ASGI conversions are now in place for `SecurityHeadersMiddleware`, `LoggingMiddleware`, `TimezoneMiddleware`, and `ContextMiddleware`.
  - **`IdempotencyMiddleware` is intentionally excluded from this remediation pass** and remains on `BaseHTTPMiddleware`.
  - Reason for exclusion: its hot-path cost is likely dominated by request-body reads, hashing, Redis coordination, and response capture/replay rather than the wrapper alone; without profiling that shows a meaningful gain, a pure-ASGI rewrite would add complexity and regression risk for unclear benefit.
  - Treat this as an intentional, documented exception unless targeted profiling later shows that rewriting `IdempotencyMiddleware` is worth the added complexity.

## Remaining gaps / recommended follow-up

- **PERF-007 — Replace offset pagination on large datasets with cursor/keyset pagination where deep paging matters**
  - The audit item is still architectural/API-level work; no repository-wide cursor pagination rollout is in place yet.

- **PERF-008 — Move long-running AI work off the request lifecycle**
  - This still needs background job / queue architecture and was not completed in the current remediation pass.

## Validation notes

- `uv run pytest tests/middleware/test_pure_asgi_middlewares.py` ✅
- `uv run pytest tests/main/test_main.py::test_root_endpoint` ✅
- `uv run pytest tests/auth/test_token_blacklist.py` ✅ (`7 passed`)
- `sh -n scripts/start-prod.sh` ✅
- `bash -n scripts/run.sh` ✅
- `docker compose ... config --no-interpolate` ✅ for both compose files
