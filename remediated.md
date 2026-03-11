# Confirmed completed audit items

## Performance remediations

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

## Security remediations completed in this pass

- [x] **SEC-003 — Fix `SECRET_KEY` sentinel validation**
  - `app/configs/settings.py` now rejects both known insecure default sentinel values in production.

- [x] **SEC-005 — Protect legacy operational endpoints**
  - `GET /health` and `GET /metrics/legacy` now require authenticated admin access in `app/routes/health.py`.
  - Public probe guidance is updated to use `GET /health/live` and `GET /health/ready`.

- [x] **SEC-007 — Replace wildcard CORS headers**
  - `app/middleware/middleware.py` now uses an explicit `allow_headers` allowlist and includes `PATCH` in allowed methods.

- [x] **SEC-008 — Add missing security headers**
  - `SecurityHeadersMiddleware` now adds `Content-Security-Policy`, `Permissions-Policy`, and `X-DNS-Prefetch-Control`.

- [x] **SEC-009 — Validate `X-Client-Timezone`**
  - `app/middleware/timezone.py` now accepts only valid IANA timezone names and falls back to `UTC` for invalid values.

- [x] **SEC-010 — Prefer authenticated identity in rate limiting**
  - `app/dependencies/dependencies.py` stores the verified user ID on `request.state`, and `app/managers/rate_limiter.py` now prefers that identity over caller-supplied API keys.

- [x] **SEC-011 — Remove eager `rich.print` import from config path**
  - `app/configs/security.py` now imports `rich.print` only inside the local debug-print function.

- [x] **SEC-013 — Reduce PII exposure in logs**
  - Logging now masks client IPs, and `app/services/email_inquiry.py` no longer logs end-user names alongside raw IP addresses.

## Deferred security items

- **SEC-001 — Active use of `python-jose`**
  - Deferred because remediation requires a dependency/runtime JWT library change and compatibility verification; no package changes were made in this pass.

- **SEC-002 — HS256 symmetric signing**
  - Deferred because moving to asymmetric signing requires coordinated key generation, secure distribution, and token validation rollout beyond a safe code-only change.

- **SEC-004 — OAuth redirect URI allowlist enforcement**
  - Deferred because it needs explicit redirect allowlist configuration and product/environment decisions for permitted callback targets.

- [x] **SEC-006 — `UserDBDep` vs `UserRespDep` audit and fix**
  - Fixed in `app/dependencies/dependencies.py` by adding `get_current_user_response` dependency that properly converts `UserDB` to `UserResponse` using the existing `validate_user_response` function.
  - Updated test in `tests/auth/test_auth_routes.py` to override the new dependency for proper test isolation.

- **SEC-012 — Secret rotation / KMS integration**
  - Deferred because it depends on infrastructure and operational secret-management changes outside the repository alone.

## Remaining gaps / recommended follow-up

- **PERF-007 — Replace offset pagination on large datasets with cursor/keyset pagination where deep paging matters**
  - The audit item is still architectural/API-level work; no repository-wide cursor pagination rollout is in place yet.

- **PERF-008 — Move long-running AI work off the request lifecycle**
  - This still needs background job / queue architecture and was not completed in the current remediation pass.

## Validation notes

- `uv run pytest tests/auth/ tests/main/` ✅ (`154 passed`)

- `uv run pytest tests/middleware/test_pure_asgi_middlewares.py tests/main/test_main.py tests/managers/test_rate_limiter.py tests/utils/test_helpers.py tests/unit/test_settings_security.py` ✅ (`36 passed`)
- `uv run pytest tests/auth/test_token_blacklist.py` ✅ (`7 passed`)
- Earlier performance verification retained from the prior remediation pass:
  - `uv run pytest tests/main/test_main.py::test_root_endpoint` ✅
- `sh -n scripts/start-prod.sh` ✅
- `bash -n scripts/run.sh` ✅
- `docker compose ... config --no-interpolate` ✅ for both compose files
