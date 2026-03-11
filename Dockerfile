# =============================================================================
# Stage 1: Builder — install dependencies and compile bytecode
# =============================================================================
FROM python:3.13-slim AS builder

# Install uv from the official image (faster than pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Pre-compile bytecode for faster cold starts
    UV_COMPILE_BYTECODE=1 \
    # Use copy mode to avoid issues with Docker mounts
    UV_LINK_MODE=copy \
    # Disable cache to reduce image size
    UV_NO_CACHE=1

WORKDIR /app

# --- Dependency caching layer ---
# Copy only dependency files first to maximize Docker layer caching.
# Dependencies change rarely; source code changes often.
COPY pyproject.toml uv.lock ./

# Install production deps without installing the project itself
RUN uv sync --frozen --no-dev --no-install-project

# --- Application source ---
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Final sync to install the project package with its entry points
RUN uv sync --frozen --no-dev


# =============================================================================
# Stage 2: Production — minimal runtime image (default target)
# =============================================================================
FROM python:3.13-slim AS production

LABEL org.opencontainers.image.title="BaliBlissed Backend" \
      org.opencontainers.image.description="BaliBlissed FastAPI Backend API" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.source="https://github.com/madesuryawan/BaliBlissed-Backend"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    # Point PATH to the copied venv so we can run uvicorn directly
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy only the virtual environment (pre-compiled bytecode included)
COPY --from=builder /app/.venv /app/.venv

# Copy application source and Alembic migration files
COPY --from=builder /app/app ./app
COPY --from=builder /app/alembic ./alembic
COPY --from=builder /app/alembic.ini ./
COPY scripts/start-prod.sh ./scripts/start-prod.sh

# Create non-root user and set ownership
RUN adduser -u 5678 --disabled-password --gecos "" appuser \
    && mkdir -p /app/logs /app/uploads \
    && chmod +x /app/scripts/start-prod.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Health check using Python stdlib (no external deps required)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health/live')" || exit 1

# Migrations are handled by the dedicated `migrate` service in docker-compose.
# This CMD only starts the application server.
CMD ["/app/scripts/start-prod.sh"]


# =============================================================================
# Stage 3: Development — hot-reload with dev dependencies
# =============================================================================
FROM builder AS development

# Install ALL dependencies (including dev) on top of the builder
RUN uv sync --frozen

# Create non-root user
RUN adduser -u 5678 --disabled-password --gecos "" appuser \
    && mkdir -p /app/logs /app/uploads \
    && chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health/live')" || exit 1

# Development command with hot reload (single worker, auto-reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--loop", "uvloop", "--log-level", "debug"]