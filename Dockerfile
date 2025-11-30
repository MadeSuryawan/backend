# Use an official Python runtime as a parent image
FROM python:3.13-slim

# 1. Install 'uv' directly from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Compile bytecode during installation for faster startup
ENV UV_COMPILE_BYTECODE=1 
# Use copy mode for linking to avoid potential issue with docker mounts
ENV UV_LINK_MODE=copy 

WORKDIR /app

# 2. Install dependencies first (Caching layer)
# We copy pyproject.toml and uv.lock to leverage Docker cache.
# Note: If you haven't generated a uv.lock yet, run 'uv lock' locally first.
COPY pyproject.toml uv.lock* ./

# Sync dependencies without installing the project itself yet
# --frozen: Ensures we use the exact versions in uv.lock
# --no-dev: Skips development dependencies (pytest, etc.)
# --no-install-project: optimizing cache by not installing the app package yet
RUN uv sync --frozen --no-install-project --no-dev

# 3. Copy application code
COPY . .

# 4. Sync the project itself
RUN uv sync --frozen --no-dev

# 5. Security & Runtime
# Add the virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Create a non-root user for security
RUN adduser --disabled-password --gecos '' appuser
USER appuser

EXPOSE 8000

# Run the application using the module path 'app.main:app'
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--log-level", "info"]