# GitHub CI/CD Implementation Plan

## 1. Overview

This document outlines the architecture and implementation steps for a robust GitHub CI/CD pipeline for the BaliBlissed Backend. The goal is to automate quality assurance (linting, testing, security, type checking) and streamline deployment to **Render**.

## 2. CI Pipeline Architecture (GitHub Actions)

The CI pipeline will trigger on every `push` and `pull_request` to the `main` branch.

### Stage 1: Quality Assurance (QA)

- **Linting & Formatting**: `uv run ruff check .` and `uv run ruff format --check .`.
- **Type Checking**: `uv run pyrefly` (as per project conventions).
- **Security Audit**:
  - `uv run bandit -r app/`: Scans for common security issues in Python code.
  - `uv run safety check`: Scans dependencies for known vulnerabilities.

### Stage 2: Automated Testing

- **Suite**: `uv run pytest`
- **Environment**: Executes in a containerized environment with access to a temporary Redis/Postgres setup if required, or uses mocked services.
- **Coverage**: Minimum 80% coverage threshold enforcement.

### Stage 3: Dockerized Build

- **Target**: `production` stage in `Dockerfile`.
- **Artifact**: Tagged image (e.g., `baliblissed:latest` and `baliblissed-${GITHUB_SHA}`).

## 3. CD Pipeline (Deployment to Render)

### Deployment Strategy

We will utilize Render's native GitHub integration or the Render API for more controlled deployments.

- **Trigger**: Success of the CI pipeline on the `main` branch.
- **Auto-Deploy**: Enabled on Render for the `main` branch.
- **Database Migrations**: Handled by the `migrate` service in production or via a pre-deploy command:

  ```bash
  alembic upgrade head
  ```

### Required GitHub Secrets

The following secrets must be configured in the GitHub repository settings:

| Secret Name | Description |
| :--- | :--- |
| `RENDER_API_KEY` | To trigger deployments via Render API (if not using auto-deploy). |
| `RENDER_SERVICE_ID` | The ID of the BaliBlissed backend service on Render. |
| `DATABASE_URL` | Production Postgres connection string (for migrations). |
| `REDIS_URL` | Production Redis connection string. |
| `SECRET_KEY` | JWT signing key. |
| `CLOUDINARY_CLOUD_NAME` | Media storage. |
| `CLOUDINARY_API_KEY` | Media storage. |
| `CLOUDINARY_API_SECRET` | Media storage. |
| `GEMINI_API_KEY` | AI Integration. |

## 4. Implementation Steps

1. **Repository Setup**: Add the required secrets to GitHub.
2. **Workflow Update**: Modify `.github/workflows/test.yml` to include the QA and Security jobs.
3. **Render Configuration**:
    - Connect the GitHub repository to the Render Web Service.
    - Reference the `Dockerfile` with the `production` target.
    - Set environment variables in the Render dashboard.
4. **Verification**: Confirm that a push to `main` triggers the full pipeline and updates the Render deployment.

## 5. Rollback Strategy

- Render supports instant rollbacks to previous successful deploys via their dashboard.
- Database rollbacks should be handled carefully via `alembic downgrade`.
