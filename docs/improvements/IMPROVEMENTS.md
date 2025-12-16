# 🚀 BaliBlissed Backend – Comprehensive Improvements Roadmap

## 📋 Overview

This document outlines a comprehensive, prioritized list of improvements for the BaliBlissed Backend application. Each improvement is categorized by priority, complexity, and impact, with detailed implementation guidance.

## 🎯 Priority Matrix

| Priority | Focus                             | Timeline                 |
| -------- | --------------------------------- | ------------------------ |
| P0       | Critical for production readiness | Immediate (1–2 weeks)    |
| P1       | High-value features               | Short-term (2–4 weeks)   |
| P2       | Quality of life improvements      | Medium-term (1–2 months) |
| P3       | Nice-to-have enhancements         | Long-term (2–3 months)   |

## 🔴 P0: Critical Production Requirements

### 1. JWT Authentication & Authorization System

- Priority: P0 | Complexity: High | Impact: Critical

#### Current State

- No authentication mechanism implemented
- Routes use basic `X-API-Key` header for rate limiting tiers
- Password hashing exists but no login/token system
- User model has `is_active` and `is_verified` flags but no enforcement

#### Implementation Requirements

##### Phase 1: JWT Infrastructure

- Install dependencies: `python-jose[cryptography]`, `passlib[bcrypt]` ([python-jose](https://python-jose.readthedocs.io/en/latest/), [Passlib](https://passlib.readthedocs.io/en/stable/))
- Create `app/auth/jwt.py`:
  - `create_access_token()` – Generate JWT tokens
  - `create_refresh_token()` – Generate refresh tokens
  - `verify_token()` – Validate and decode tokens
- Token expiration: 30 minutes (access), 7 days (refresh)
- Create `app/auth/dependencies.py`:
  - `get_current_user()` – Extract user from token
  - `get_current_active_user()` – Verify user is active
  - `require_verified_user()` – Verify user email is verified

##### Phase 2: Authentication Endpoints

- Create `app/routes/auth.py`:
  - `POST /auth/register` – User registration
  - `POST /auth/login` – Login with username/password
  - `POST /auth/refresh` – Refresh access token
  - `POST /auth/logout` – Invalidate tokens (blacklist)
  - `POST /auth/verify-email` – Email verification
  - `POST /auth/forgot-password` – Password reset request
  - `POST /auth/reset-password` – Password reset confirmation

##### Phase 3: Token Blacklist

- Add Redis-based token blacklist for logout ([Redis](https://redis.io/))
- Store revoked tokens with TTL matching token expiration
- Check blacklist in `verify_token()`

##### Phase 4: Protected Routes

- Add `Depends(get_current_user)` to protected endpoints
- Update user routes to require authentication
- Update blog routes to verify author ownership

##### Files to Create/Modify

- `app/auth/__init__.py`
- `app/auth/jwt.py`
- `app/auth/dependencies.py`
- `app/routes/auth.py`
- `app/schemas/auth.py` (LoginRequest, TokenResponse, etc.)
- `app/routes/user.py` (add auth dependencies)
- `app/routes/blog.py` (add auth dependencies)

---

### 2. Database Migrations with Alembic

- Priority: P0 | Complexity: Medium | Impact: Critical

#### Current State

- Using `SQLModel.metadata.create_all()` for table creation ([SQLModel](https://sqlmodel.tiangolo.com/))
- No migration history or version control
- Comment in code: "For production, use proper migration tools like Alembic"
- Alembic is installed in dependencies but not configured ([Alembic](https://alembic.sqlalchemy.org/en/latest/))

#### Implementation Requirements

##### Phase 1: Alembic Setup

```bash
# Initialize Alembic
uv run alembic init alembic

# Configure alembic.ini
# Set sqlalchemy.url to use settings.DATABASE_URL
```

##### Phase 2: Configuration

- Create `alembic/env.py`:
  - Import SQLModel metadata
  - Import all models (`UserDB`, `BlogDB`)
  - Configure async engine
  - Set `target_metadata = SQLModel.metadata`

##### Phase 3: Initial Migration

```bash
# Create initial migration
uv run alembic revision --autogenerate -m "Initial schema"

# Review generated migration

# Apply migration
uv run alembic upgrade head
```

##### Phase 4: Migration Workflow

- Remove `await conn.run_sync(SQLModel.metadata.create_all)` from `app/db/init_db.py`
- Update `app/db/init_db.py` to run migrations instead
- Add migration commands to `scripts/migrate.sh`
- Update Docker entrypoint to run migrations on startup

##### Phase 5: Documentation

- Create `docs/MIGRATIONS.md`:
  - How to create migrations
  - How to apply migrations
  - How to rollback migrations
  - Migration best practices

##### Files to Create/Modify

- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/` (migration files)
- `app/db/init_db.py` (remove create_all)
- `scripts/migrate.sh`
- `Dockerfile` (add migration step)
- `docs/MIGRATIONS.md`

---

### 3. Role-Based Access Control (RBAC)

- Priority: P0 | Complexity: High | Impact: High

#### Current State

- No role system implemented
- Admin operations check for localhost only (`host(request)` in `("127.0.0.1", "::1", "localhost")`)
- No permission granularity

#### Implementation Requirements

##### Phase 1: Role Model

- Create `app/models/role.py`:
  - `RoleDB` model with permissions JSON field
  - Predefined roles: `admin`, `editor`, `user`, `guest`
- Add `role` field to `UserDB` model (default: `"user"`)
- Create migration for `role` column

##### Phase 2: Permission System

- Create `app/auth/permissions.py`:
  - Permission enum (`READ`, `WRITE`, `DELETE`, `ADMIN`)
  - `has_permission()` – Check user permissions
  - `require_permission()` – Dependency for routes
  - `require_role()` – Dependency for role-based access

##### Phase 3: Permission Decorators

- Create `app/decorators/permissions.py`:
  - `@require_admin` – Admin-only routes
  - `@require_owner_or_admin` – Owner or admin access
  - `@require_permission(Permission.WRITE)` – Permission-based

##### Phase 4: Update Routes

- Replace localhost checks with `@require_admin`
- Add owner checks for blog/user updates
- Add permission checks for sensitive operations

##### Phase 5: Admin Interface

- Create `app/routes/admin.py`:
  - `GET /admin/users` – List all users
  - `PUT /admin/users/{id}/role` – Update user role
  - `GET /admin/stats` – System statistics

##### Files to Create/Modify

- `app/models/role.py`
- `app/models/user.py` (add role field)
- `app/auth/permissions.py`
- `app/decorators/permissions.py`
- `app/routes/admin.py`
- `app/routes/user.py` (add permission checks)
- `app/routes/blog.py` (add ownership checks)
- `alembic/versions/xxx_add_roles.py` (migration)

## 🟠 P1: High-Value Features

### 1. Comprehensive Monitoring & Observability

- Priority: P1 | Complexity: Medium | Impact: High

#### Current State

- Basic metrics in `app/managers/metrics.py`
- Health check endpoint exists
- Logging to file with JSON format
- No centralized monitoring or alerting

#### Implementation Requirements

##### Phase 1: Prometheus Metrics

- Install: `prometheus-client`, `prometheus-fastapi-instrumentator` ([Prometheus](https://prometheus.io/), [Prometheus FastAPI Instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator))
- Create `app/monitoring/prometheus.py`:
  - Instrument FastAPI app ([FastAPI](https://fastapi.tiangolo.com/))
  - Custom metrics: cache hit rate, AI request duration, circuit breaker state
  - Export endpoint: `GET /metrics` (Prometheus format)
- Add metrics to:
  - Cache operations (hits, misses, latency)
  - AI requests (duration, errors, token usage)
  - Database queries (duration, errors)
  - Circuit breaker state changes

##### Phase 2: Structured Logging

- Install: `structlog` ([structlog](https://www.structlog.org/en/stable/))
- Create `app/monitoring/logging.py`:
  - Configure structlog with JSON output
  - Add request ID to all logs
  - Add user context to logs (when authenticated)
  - Log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

##### Phase 3: Distributed Tracing

- Install: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi` ([OpenTelemetry](https://opentelemetry.io/))
- Create `app/monitoring/tracing.py`:
  - Configure OpenTelemetry
  - Trace AI requests
  - Trace database queries
  - Trace cache operations
  - Export to Jaeger or Zipkin ([Jaeger](https://www.jaegertracing.io/), [Zipkin](https://zipkin.io/))

##### Phase 4: Health Checks

- Enhance `app/main.py` health endpoint:
  - Database connectivity check
  - Redis connectivity check
  - AI service availability
  - Email service availability
  - Disk space check
  - Memory usage check
  - Add liveness and readiness probes for Kubernetes

##### Phase 5: Alerting

- Create `app/monitoring/alerts.py`:
  - Alert on high error rate
  - Alert on circuit breaker open
  - Alert on database connection failures
  - Alert on high latency
  - Configure alert destinations (email, Slack, PagerDuty)

##### Phase 6: Grafana Dashboards

- Create `monitoring/grafana/dashboards/`:
  - `overview.json` – System overview
  - `api.json` – API performance
  - `cache.json` – Cache statistics
  - `ai.json` – AI service metrics
  - `errors.json` – Error tracking

##### Files to Create/Modify

- `app/monitoring/__init__.py`
- `app/monitoring/prometheus.py`
- `app/monitoring/logging.py`
- `app/monitoring/tracing.py`
- `app/monitoring/alerts.py`
- `app/main.py` (enhance health check)
- `monitoring/grafana/dashboards/` (dashboard configs)
- `monitoring/prometheus.yml` (Prometheus config)
- `docker-compose.yaml` (add Prometheus, Grafana, Jaeger)

---

## Version History

- 2025-12-11 — Reformatted document for structured markdown (headers, bullets, tables, code blocks, links). All original content retained.
