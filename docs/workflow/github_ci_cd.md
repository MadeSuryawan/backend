# GitHub CI/CD Pipeline — Operational Documentation

> **Canonical reference** for the BaliBlissed Backend CI/CD pipeline.
> For the design rationale and revision history, see `docs/plan/github_ci_cd.md` (archived).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Pipeline Architecture](#2-pipeline-architecture)
3. [CI Pipeline — Job Reference](#3-ci-pipeline--job-reference)
4. [CD Pipeline — Job Reference](#4-cd-pipeline--job-reference)
5. [One-Time Setup Guide](#5-one-time-setup-guide)
6. [Secrets Reference](#6-secrets-reference)
7. [Environment Variables in CI](#7-environment-variables-in-ci)
8. [Branching, Trigger Rules & Activation Guide](#8-branching-trigger-rules--activation-guide)
9. [Artifacts & Reports](#9-artifacts--reports)
10. [Security Architecture](#10-security-architecture)
11. [Performance & Caching](#11-performance--caching)
12. [Rollback Procedures](#12-rollback-procedures)
13. [Maintenance Guide](#13-maintenance-guide)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Overview

The pipeline consists of two GitHub Actions workflow files:

| File | Purpose | Current State | Full Auto-Run State |
| :--- | :--- | :--- | :--- |
| `.github/workflows/ci.yml` | Quality, security, tests, Docker build & scan | **Manual only** (`workflow_dispatch`) | `push`/`PR` to `main` + manual |
| `.github/workflows/cd.yml` | Production deployment to Render | **Manual only** (`workflow_dispatch`) | After CI succeeds on `main` + manual |

> **Current Status — Manual Only**: Both workflows are intentionally gated to manual dispatch while the pipeline is being validated. See [§8 — Activation Guide](#8-branching-trigger-rules--activation-guide) for how to run them manually and how to enable auto-run when ready.

**Key principles:**

- Zero long-lived credentials for the container registry (uses `GITHUB_TOKEN` with OIDC)
- Minimum two secrets stored in GitHub (`RENDER_API_KEY`, `RENDER_SERVICE_ID`)
- All application secrets live only in Render's environment configuration
- Every PR gets full CI feedback before merge; once auto-run is enabled, every merge to `main` deploys automatically

---

## 2. Pipeline Architecture

```text
Push / PR to main
       │
       ▼
  ┌────────────────────────────────────────────────────────┐
  │                    ci.yml (CI Pipeline)                │
  │                                                        │
  │  ┌───────────┐  ┌───────────┐  ┌──────────────────┐   │
  │  │  quality  │  │   test    │  │    security      │   │
  │  │           │  │           │  │                  │   │
  │  │ ruff check│  │  pytest   │  │  pip-audit       │   │
  │  │ ruff fmt  │  │testcontain│  │  (dep CVE scan)  │   │
  │  │ pyrefly   │  │  ers +    │  │                  │   │
  │  │           │  │ coverage  │  │                  │   │
  │  └─────┬─────┘  └─────┬─────┘  └────────┬─────────┘   │
  │        └──────────────┴─────────────────┘             │
  │                         │                             │
  │              ┌──────────▼──────────┐                  │
  │              │   build-and-scan    │                  │
  │              │                    │                  │
  │              │  Docker build      │                  │
  │              │  → GHCR push(main) │                  │
  │              │  → Trivy scan      │                  │
  │              │  → SARIF upload    │                  │
  │              └─────────────────────┘                  │
  └────────────────────────────────────────────────────────┘
                         │ (push to main only)
                         ▼
  ┌────────────────────────────────────────────────────────┐
  │                   cd.yml (CD Pipeline)                 │
  │                                                        │
  │              ┌──────────────────────┐                  │
  │              │        deploy        │                  │
  │              │                    │                  │
  │              │  Render API POST   │                  │
  │              │  Poll until live   │                  │
  │              │  Write summary     │                  │
  │              └──────────────────────┘                  │
  └────────────────────────────────────────────────────────┘
```

**Parallelism**: `quality`, `test`, and `security` jobs run simultaneously.  
Total CI wall-clock time ≈ `max(quality_time, test_time, security_time) + build_scan_time`.

---

## 3. CI Pipeline — Job Reference

### `quality` — Code Quality

**Runner**: `ubuntu-latest` | **Permissions**: `contents: read`

| Step | Command | What it checks |
| :--- | :--- | :--- |
| Lint | `uv run ruff check . --output-format=github` | Style, imports, complexity, security (S rules = bandit-equivalent) |
| Format | `uv run ruff format --check .` | Code formatting consistency |
| Type check | `uv run pyrefly check` | Static type correctness |

> `ruff`'s `S` rule set is configured in `pyproject.toml` and covers the same checks as `bandit` — no separate bandit invocation is needed.

**Failure behavior**: Any lint error, format violation, or type error fails the job and blocks the `build-and-scan` job.

---

### `test` — Automated Tests

**Runner**: `ubuntu-latest` (Docker pre-installed) | **Permissions**: `contents: read`

| Step | Details |
| :--- | :--- |
| Database | `testcontainers` spins up `postgres:15-alpine` in `conftest.py`. Overwrites `DATABASE_URL` before any app import. |
| Redis | Disabled (`REDIS_ENABLED=false`). App uses `IN_MEMORY_FALLBACK_ENABLED=true`. |
| Command | `uv run pytest --cov=app --cov-fail-under=80 --cov-report=xml --cov-report=html` |
| Coverage gate | Build fails if `app/` coverage < 80% |
| Artifacts | HTML report + XML uploaded (14-day retention) |

**Why Docker works in CI**: GitHub's `ubuntu-latest` runners include Docker Engine. `testcontainers` communicates with it via the standard Docker socket — no additional setup required.

---

### `security` — Dependency Vulnerability Scan

**Runner**: `ubuntu-latest` | **Permissions**: `contents: read`

| Step | Details |
| :--- | :--- |
| Tool | `pip-audit` (PyPA, free, OSV + PyPI Advisory databases) |
| Scope | Production dependencies only (`--no-dev`) |
| Command | `uv export --no-dev --format requirements-txt \| uvx pip-audit -r /dev/stdin` |
| `uvx` | Runs `pip-audit` in an ephemeral environment — nothing installed into the project venv |

**Failure behavior**: Any known CVE in production dependencies fails the job.

---

### `build-and-scan` — Docker Build & Container Security

**Runner**: `ubuntu-latest` | **Permissions**: `contents: read`, `packages: write`, `security-events: write`  
**Depends on**: `quality`, `test`, `security` (all must pass)

| Step | On `push` to `main` | On `pull_request` |
| :--- | :--- | :--- |
| GHCR login | ✅ (GITHUB_TOKEN) | ✅ (GITHUB_TOKEN) |
| Docker build | ✅ target: `production` | ✅ target: `production` |
| Image push to GHCR | ✅ tags: `:sha`, `:latest` | ❌ (loaded locally only) |
| Trivy scan | ✅ scans pushed image | ✅ scans local image |
| SARIF upload | ✅ GitHub Security tab | ✅ GitHub Security tab |

**Image tags** (on `main` push):

- `ghcr.io/<owner>/baliblissed-backend:<full-git-sha>`
- `ghcr.io/<owner>/baliblissed-backend:latest`

**Trivy configuration**:

- Severity filter: `CRITICAL`, `HIGH` only
- `ignore-unfixed: true` — skips CVEs with no available fix
- Exit code `1` on findings (fails the build)

---

## 4. CD Pipeline — Job Reference

### `deploy` — Production Deployment

**Runner**: `ubuntu-latest` | **Permissions**: `contents: read`  
**Environment**: `production` (GitHub Environments)  
**Trigger**: `workflow_run` completion (CI success on `main`), or manual `workflow_dispatch`

| Step | Details |
| :--- | :--- |
| Guard condition | Skips if CI did not succeed or branch ≠ `main` |
| API call | `POST https://api.render.com/v1/services/{id}/deploys` |
| Poll | Checks status every 15s, timeout 15 min |
| Terminal states | `live` = success; `failed`/`cancelled`/`timed_out` = failure |
| Summary | Writes deploy URL and status to the GitHub Actions job summary |

**Database migrations**: Render is configured with a pre-deploy command (`alembic upgrade head`) that runs in the production environment before the new instance starts. This is safer than running migrations from CI.

---

## 5. One-Time Setup Guide

### Step 1 — GitHub Secrets

Navigate to: **Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | Value | Where to find |
| :--- | :--- | :--- |
| `RENDER_API_KEY` | Your Render API token | Render Dashboard → Account → API Keys |
| `RENDER_SERVICE_ID` | Your service ID (e.g. `srv-xxxx`) | Render service URL or API |

### Step 2 — GitHub Environment (Optional but recommended)

1. Go to **Repository → Settings → Environments → New environment**
2. Name it exactly `production`
3. (Optional) Add **Required reviewers** — all deployments will wait for approval
4. (Optional) Add a **Wait timer** (e.g. 5 min) as a deployment circuit breaker

### Step 3 — Render Service Configuration

In your Render Web Service settings:

1. **Build Command**: Leave as Docker (Render detects `Dockerfile` automatically)
2. **Dockerfile target**: `production`
3. **Pre-deploy Command**: `alembic upgrade head`
4. **Auto-deploy**: Disable (CI/CD pipeline handles deploys via API)
5. **Environment Variables**: Add all production secrets here (see §6 for list)

### Step 4 — GitHub Container Registry (GHCR)

GHCR is enabled automatically for any repository with GitHub Actions. After the first successful push to `main`, the package `baliblissed-backend` will appear under your account's **Packages**.

To set visibility: **Account → Packages → baliblissed-backend → Package settings → Change visibility**

### Step 5 — Branch Protection (Recommended)

Enable branch protection on `main`:

1. **Repository → Settings → Branches → Add branch ruleset**
2. Require status checks: `quality`, `test`, `security`, `build-and-scan`
3. Require branches to be up to date before merging
4. Restrict force pushes

---

## 6. Secrets Reference

### GitHub Secrets (stored in GitHub)

| Secret | Required | Used In | Description |
| :--- | :--- | :--- | :--- |
| `RENDER_API_KEY` | ✅ | `cd.yml` | Render personal API token for triggering deploys |
| `RENDER_SERVICE_ID` | ✅ | `cd.yml` | Render service identifier (format: `srv-xxxx`) |
| `GITHUB_TOKEN` | Auto | `ci.yml` | Auto-provided by GitHub; used for GHCR push and SARIF upload |

### Render Environment Variables (stored in Render, NOT GitHub)

Configure these in the Render dashboard under your service's Environment settings:

| Variable | Required | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | ✅ | Production PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `SECRET_KEY` | ✅ | JWT signing key (min 32 chars, cryptographically random) |
| `ENVIRONMENT` | ✅ | Set to `production` |
| `REDIS_HOST` | ✅ | Production Redis hostname |
| `REDIS_PORT` | ✅ | Production Redis port |
| `REDIS_PASSWORD` | ✅ | Production Redis password |
| `REDIS_SSL` | ✅ | Set to `true` in production |
| `CLOUDINARY_CLOUD_NAME` | If using Cloudinary | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | If using Cloudinary | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | If using Cloudinary | Cloudinary API secret |
| `GEMINI_API_KEY` | If using AI features | Google Gemini API key |
| `TRUSTED_HOSTS` | ✅ | Your production domain(s), comma-separated |
| `CORS_ORIGINS` | ✅ | Allowed frontend origins, comma-separated |
| `PRODUCTION_FRONTEND_URL` | Recommended | Production frontend URL |

---

## 7. Environment Variables in CI

The CI pipeline uses **minimal, safe defaults** — no production secrets are needed:

| Variable | Value in CI | Reason |
| :--- | :--- | :--- |
| `DATABASE_URL` | Placeholder (overridden) | `conftest.py` overwrites this with the testcontainers PostgreSQL URL before any import |
| `REDIS_ENABLED` | `false` | Redis not available; app uses `IN_MEMORY_FALLBACK_ENABLED=true` |
| `ENVIRONMENT` | `test` | Prevents production-only validators from raising errors |
| `SECRET_KEY` | Default (`dev-only-insecure-key-replace-in-prod`) | Validator only raises in `ENVIRONMENT=production` |
| All other secrets | `None` defaults in `settings.py` | All application secrets are `Optional` |

---

## 8. Branching, Trigger Rules & Activation Guide

### 8.1 Current State — Manual Only

Both workflow files ship with auto-run triggers **commented out**. This allows the pipeline to be validated safely before it runs on every commit.

| Event | `ci.yml` runs? | `cd.yml` runs? |
| :--- | :--- | :--- |
| `push` to `main` | ❌ *(triggers commented out)* | ❌ *(triggers commented out)* |
| `pull_request` to `main` | ❌ *(triggers commented out)* | ❌ |
| `push` to any other branch | ❌ | ❌ |
| Manual `workflow_dispatch` | ✅ | ✅ |

### 8.2 How to Run Manually

Use this to validate the pipeline before enabling auto-run.

**Run CI manually:**

1. Go to **GitHub → Actions → CI Pipeline**
2. Click **Run workflow** (top-right dropdown)
3. Select branch `main` → click **Run workflow**
4. Wait for all 4 jobs (`quality`, `test`, `security`, `build-and-scan`) to turn green ✅

**Run CD manually:**

1. Ensure `RENDER_API_KEY` and `RENDER_SERVICE_ID` are added to GitHub Secrets (see §6)
2. Go to **GitHub → Actions → CD Pipeline**
3. Click **Run workflow**
4. Fill in an optional **Reason** (e.g. `"Initial validation deploy"`)
5. Click **Run workflow** and monitor the deploy log + Render dashboard

### 8.3 How to Enable Auto-Run

Once both manual runs succeed, uncomment the trigger blocks in each file.

**Step 1 — Enable CI auto-run** (edit `.github/workflows/ci.yml`):

```yaml
# Before (manual only):
on:
    workflow_dispatch:
    # push:
    #     branches: ["main"]
    # pull_request:
    #     branches: ["main"]

# After (auto-run enabled):
on:
    workflow_dispatch:
    push:
        branches: ["main"]
    pull_request:
        branches: ["main"]
```

**Step 2 — Enable CD auto-run** (edit `.github/workflows/cd.yml`):

```yaml
# Before (manual only):
on:
    # workflow_run:
    #   workflows: ["CI Pipeline"]
    #   types: [completed]
    #   branches: ["main"]
    workflow_dispatch:

# After (auto-run enabled):
on:
    workflow_run:
        workflows: ["CI Pipeline"]
        types: [completed]
        branches: ["main"]
    workflow_dispatch:
```

**Step 3** — Commit and push both files to `main`. From that push onward, the full pipeline runs automatically on every push and PR.

### 8.4 Full Auto-Run Behaviour (after activation)

| Event | `ci.yml` runs? | `cd.yml` runs? |
| :--- | :--- | :--- |
| `push` to `main` | ✅ Full CI (image pushed to GHCR) | ✅ After CI succeeds |
| `pull_request` to `main` | ✅ Full CI (image loaded locally, not pushed) | ❌ |
| `push` to any other branch | ❌ | ❌ |
| Manual `workflow_dispatch` | ✅ | ✅ (with optional reason input) |

### 8.5 Recommended Activation Sequence

```text
1. Push workflow files as-is (manual-only triggers)
2. Run ci.yml manually → verify all 4 jobs pass
3. Add RENDER_API_KEY + RENDER_SERVICE_ID to GitHub Secrets
4. Run cd.yml manually → verify Render deploy reaches "live"
5. Uncomment triggers in both files → push to main
6. Auto-run is now live for all future pushes and PRs
```

**Concurrency**: Each workflow cancels older in-progress runs on the same ref to avoid wasted runner minutes.

---

## 9. Artifacts & Reports

| Artifact | Job | Retention | Content |
| :--- | :--- | :--- | :--- |
| `coverage-report-<sha>` | `test` | 14 days | HTML coverage report (`htmlcov/`) |
| `coverage-xml-<sha>` | `test` | 14 days | `coverage.xml` for external tools |
| Trivy SARIF | `build-and-scan` | Permanent | GitHub Security → Code Scanning Alerts |

**Viewing coverage**: Download the `coverage-report-<sha>` artifact from the Actions run, extract it, and open `htmlcov/index.html` in a browser.

---

## 10. Security Architecture

### Credential Principles

1. **GHCR authentication**: Uses `GITHUB_TOKEN` (auto-provided, scoped to the job, expires when the job ends). No stored credentials.
2. **Render API key**: Stored as a GitHub Secret; only accessible to workflows in this repository. Scoped to the `cd.yml` deploy job.
3. **No production secrets in CI**: All production environment variables live exclusively in Render's dashboard. The CI pipeline cannot access them.

### Least-Privilege Permissions

```yaml
# Workflow default
permissions:
  contents: read      # All jobs: read code only

# build-and-scan overrides:
  packages: write     # Push image to GHCR
  security-events: write  # Upload SARIF results

# All other jobs use the default (contents: read only)
```

### Vulnerability Scanning Layers

| Layer | Tool | Scope | Failure Mode |
| :--- | :--- | :--- | :--- |
| Code security | `ruff` S rules (bandit-equivalent) | Python source | Lint failure |
| Dependency CVEs | `pip-audit` | Production Python packages | Security job failure |
| Container CVEs | Trivy | OS packages + Python packages in image | Build-and-scan failure |

---

## 11. Performance & Caching

| Cache | Key | Scope | Effect |
| :--- | :--- | :--- | :--- |
| uv package cache | `uv.lock` hash | Per job (shared via Actions cache) | ~60s saved when lockfile unchanged |
| Docker layer cache | GHA cache backend | `build-and-scan` job | ~2–4 min saved for unchanged layers |

**Cache invalidation**:

- uv cache: automatically invalidated when `uv.lock` changes
- Docker cache: invalidated when any `COPY` source changes (dependency files first, then app code — see Dockerfile layer ordering)

---

## 12. Rollback Procedures

### Application Rollback

**Option A — Render Dashboard (fastest, ~30s)**:

1. Render Dashboard → your service → **Deploys** tab
2. Find a previous successful deploy → click **Rollback to this deploy**

**Option B — Git Revert (clean audit trail)**:

```bash
git revert <commit-sha>
git push origin main
# CI/CD runs automatically and deploys the reverted commit
```

**Option C — Manual CD dispatch**:
After reverting, trigger `cd.yml` manually from **Actions → CD Pipeline → Run workflow**.

### Database Rollback

> ⚠️ Always snapshot the database before any production migration.

```bash
# SSH into the Render service shell (or use Render Shell in dashboard)

# Check current revision
alembic current

# Downgrade one step
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade <revision-id>

# List all revisions
alembic history --verbose
```

**Requirement**: Every Alembic migration file must implement `downgrade()`. An empty `downgrade()` makes rollback impossible.

---

## 13. Maintenance Guide

### Updating GitHub Actions Versions

Actions are pinned to major versions (`@v4`, `@v5`, etc.). Patch updates within a major version are applied automatically. To upgrade to a new major version:

1. Check the action's release notes for breaking changes
2. Update the `uses:` line in the relevant workflow file
3. Push to a branch, open a PR, verify CI passes

```bash
# Actions to keep updated:
# actions/checkout              — https://github.com/actions/checkout/releases
# astral-sh/setup-uv            — https://github.com/astral-sh/setup-uv/releases
# docker/setup-buildx-action    — https://github.com/docker/setup-buildx-action/releases
# docker/login-action           — https://github.com/docker/login-action/releases
# docker/build-push-action      — https://github.com/docker/build-push-action/releases
# docker/metadata-action        — https://github.com/docker/metadata-action/releases
# aquasecurity/trivy-action     — https://github.com/aquasecurity/trivy-action/releases
# github/codeql-action          — https://github.com/github/codeql-action/releases
# actions/upload-artifact       — https://github.com/actions/upload-artifact/releases
```

### Updating Python Version

1. Update `Dockerfile`: `FROM python:3.13-slim` → `FROM python:3.14-slim`
2. Update `pyproject.toml`: `requires-python = ">=3.14"`
3. Update both workflow files: `uv python install 3.13` → `uv python install 3.14`
4. Run `uv lock` to regenerate the lockfile

### Adding a New CI Check

1. Add a new job to `.github/workflows/ci.yml`
2. If it should block deployment, add it to `build-and-scan`'s `needs:` list
3. If it's a branch protection requirement, add it to the branch ruleset

### Adding a Staging Environment

1. Create a `develop` branch
2. Add `develop` to the `push: branches` list in `ci.yml`
3. Create a staging Render service
4. Add `RENDER_SERVICE_ID_STAGING` to GitHub Secrets
5. Add a `deploy-staging` job to `cd.yml` conditioned on `develop` branch

---

## 14. Troubleshooting

### CI fails on `quality` — pyrefly errors

```bash
# Run locally to reproduce
uv run pyrefly check

# Fix type errors, then re-push
```

### CI fails on `quality` — ruff errors

```bash
# See all issues
uv run ruff check . --output-format=full

# Auto-fix where possible
uv run ruff check . --fix
uv run ruff format .
```

### CI fails on `test` — testcontainers / Docker error

- Ensure the test runner is `ubuntu-latest` (not `macos-latest` or `windows-latest` — Docker is only pre-installed on ubuntu)
- Check if the `postgres:15-alpine` image pull failed (transient network issue — retry the job)

### CI fails on `security` — pip-audit CVE found

```bash
# See what was found
uv export --no-dev --format requirements-txt | uvx pip-audit -r /dev/stdin

# Option 1: Upgrade the vulnerable package
uv add <package>@latest
uv lock

# Option 2: If no fix available, add an exception (use sparingly)
# uvx pip-audit -r requirements-audit.txt --ignore-vuln GHSA-xxxx-xxxx-xxxx
```

### CI fails on `build-and-scan` — Trivy CVE found

```bash
# Run Trivy locally
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image \
  --severity CRITICAL,HIGH \
  --ignore-unfixed \
  ghcr.io/<owner>/baliblissed-backend:latest

# Fix: update the base image in Dockerfile
# FROM python:3.13-slim → python:3.13-slim-bookworm (or latest patch)
```

### CD fails — Render API returns non-201

1. Verify `RENDER_API_KEY` is valid and not expired (Render → Account → API Keys)
2. Verify `RENDER_SERVICE_ID` is correct (check Render service URL)
3. Check Render's status page: <https://status.render.com>

### CD polling times out (>15 min)

This usually means Render's build is taking longer than expected.

1. Check Render dashboard for the deploy's build logs
2. If it's a one-off slowdown, re-run the `cd.yml` job manually
3. If consistently slow, consider increasing `TIMEOUT=900` in `cd.yml`
