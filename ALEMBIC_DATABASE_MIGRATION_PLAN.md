# Alembic Database Migration Implementation Plan

## Executive Summary

This document outlines the implementation plan for migrating from SQLModel's `create_all()` to Alembic-managed database migrations. This is a **P0 (Critical)** requirement for production readiness.

---

## Current State Analysis

### What We Have

| Component           | Current Implementation                                           | Issue                                      |
| ------------------- | ---------------------------------------------------------------- | ------------------------------------------ |
| Table Creation      | `SQLModel.metadata.create_all()` in `app/db/database.py:126-143` | No version control, no rollback capability |
| Models              | `UserDB`, `BlogDB` with SQLModel                                 | Well-defined, ready for Alembic            |
| Database Driver     | `asyncpg` (async PostgreSQL)                                     | Requires async Alembic config              |
| Alembic Dependency  | Installed (`alembic>=1.17.2` in pyproject.toml)                  | Not configured                             |
| Connection Settings | `app/configs/settings.py`                                        | `DATABASE_URL` ready to use                |

### Models to Migrate

#### 1. UserDB (`app/models/user.py`)

```plain test
Table: users
├── uuid (PK, UUID)
├── username (VARCHAR(50), UNIQUE, INDEX)
├── email (VARCHAR(255), UNIQUE, INDEX)
├── password_hash (VARCHAR(255), NULLABLE)
├── auth_provider (VARCHAR(50), DEFAULT 'email')
├── provider_id (VARCHAR(255), NULLABLE, INDEX)
├── first_name (VARCHAR(100), NULLABLE)
├── last_name (VARCHAR(100), NULLABLE)
├── bio (VARCHAR(160), NULLABLE)
├── profile_picture (VARCHAR(500), NULLABLE)
├── website (VARCHAR(500), NULLABLE)
├── date_of_birth (VARCHAR(10), NULLABLE)
├── gender (VARCHAR(50), NULLABLE)
├── phone_number (VARCHAR(20), NULLABLE)
├── country (VARCHAR(100), NULLABLE)
├── is_active (BOOLEAN, NOT NULL, DEFAULT TRUE)
├── is_verified (BOOLEAN, NOT NULL, DEFAULT FALSE)
├── role (VARCHAR(20), NOT NULL, DEFAULT 'user', INDEX)  ← NEW from JWT hardening
├── created_at (TIMESTAMP WITH TIME ZONE, NOT NULL)
└── updated_at (TIMESTAMP WITH TIME ZONE, NULLABLE)
```

#### 2. BlogDB (`app/models/blog.py`)

```plain test
Table: blogs
├── id (PK, UUID)
├── author_id (FK → users.uuid, ON DELETE CASCADE, INDEX)
├── title (VARCHAR(100), NOT NULL)
├── slug (VARCHAR(100), UNIQUE, NOT NULL, INDEX)
├── content (VARCHAR(50000), NOT NULL)
├── summary (VARCHAR(300), NULLABLE)
├── view_count (INTEGER, NOT NULL, DEFAULT 0)
├── word_count (INTEGER, NOT NULL, DEFAULT 0)
├── reading_time_minutes (INTEGER, NOT NULL, DEFAULT 0)
├── status (VARCHAR(20), NOT NULL, INDEX)
├── tags (JSONB, NOT NULL)  ← PostgreSQL-specific
├── images_url (JSONB, NULLABLE)
├── created_at (TIMESTAMP WITH TIME ZONE, NOT NULL, INDEX)
└── updated_at (TIMESTAMP WITH TIME ZONE, NULLABLE)

Indexes:
├── ix_blogs_tags_gin (GIN index on tags)
├── ix_blogs_status_created (status, created_at)
└── ix_blogs_author_status (author_id, status)
```

---

## Implementation Plan

### Phase 1: Alembic Setup

**Objective**: Initialize Alembic with async SQLModel support.

#### Files to Create

| File                     | Purpose                                     |
| ------------------------ | ------------------------------------------- |
| `alembic.ini`            | Alembic configuration (connection, logging) |
| `alembic/env.py`         | Migration environment with async engine     |
| `alembic/script.py.mako` | Migration script template                   |
| `alembic/README`         | Standard Alembic readme                     |
| `alembic/versions/`      | Migration files directory                   |

#### `alembic.ini` Configuration

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

# Use settings from app/configs/settings.py (will be overridden in env.py)
sqlalchemy.url = driver://user:pass@localhost/dbname

[post_write_hooks]
hooks = ruff_format, ruff_check
ruff_format.type = exec
ruff_format.executable = uv
ruff_format.options = run ruff format REVISION_SCRIPT_FILENAME
ruff_check.type = exec
ruff_check.executable = uv
ruff_check.options = run ruff check --fix REVISION_SCRIPT_FILENAME

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

#### `alembic/env.py` (Async Configuration)

Key requirements:

1. Import SQLModel metadata from all models
2. Configure async engine using `settings.DATABASE_URL`
3. Support both online (connected) and offline (SQL script) migrations
4. Handle PostgreSQL-specific types (JSONB, UUID)

```python
"""Alembic migration environment configuration for async SQLModel."""

from asyncio import run as asyncio_run
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from app.configs import settings
# Import all models to register them with SQLModel.metadata
from app.models import BlogDB, UserDB  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations with given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connected to database)."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio_run(run_migrations_online())
```

---

### Phase 2: Initial Migration (Existing Schema)

**Objective**: Capture existing schema as the baseline migration.

#### Decision: Empty Database vs. Existing Data

| Scenario                         | Approach                                                           |
| -------------------------------- | ------------------------------------------------------------------ |
| **New deployment (recommended)** | Generate autogenerate migration, apply to fresh DB                 |
| **Existing database with data**  | Use `--autogenerate` to detect schema, then stamp current revision |

#### Commands

```bash
# 1. Generate initial migration
uv run alembic revision --autogenerate -m "initial_schema"

# 2. Review generated migration in alembic/versions/xxx_initial_schema.py
# ⚠️ CRITICAL: Always review autogenerated migrations!

# 3a. For NEW database:
uv run alembic upgrade head

# 3b. For EXISTING database with matching schema:
uv run alembic stamp head
```

#### Expected Migration Content

The initial migration should include:

**Upgrade (create tables)**:

1. Create `users` table with all columns and indexes
2. Create `blogs` table with all columns, FK, and composite indexes
3. Create GIN index for `tags` JSONB column

**Downgrade (drop tables)**:

1. Drop `blogs` table (due to FK dependency)
2. Drop `users` table

---

### Phase 3: Update Application Startup

**Objective**: Replace `create_all()` with Alembic migrations.

#### Files to Modify

| File                           | Change                                        |
| ------------------------------ | --------------------------------------------- |
| `app/db/database.py`           | Remove `create_all()` from `init_db()`        |
| `app/middleware/middleware.py` | Add migration check/run on startup (optional) |

#### Option A: Manual Migrations (Recommended for Production)

Remove `create_all()` and require explicit `alembic upgrade head` before starting:

```python
# app/db/database.py - Modified init_db()
async def init_db() -> None:
    """
    Initialize database connection.

    Note: Database schema is managed by Alembic migrations.
    Run 'uv run alembic upgrade head' before starting the application.
    """
    # Verify connection works
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified!")
```

#### Option B: Automatic Migrations on Startup (Development Only)

```python
# app/db/database.py - Only for development
from alembic import command
from alembic.config import Config

async def init_db() -> None:
    """Initialize database with automatic migrations (development only)."""
    if settings.ENVIRONMENT == "development":
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied!")
```

---

### Phase 4: Migration Scripts

**Objective**: Create helper scripts for common migration operations.

#### `scripts/migrate.sh`

```bash
#!/bin/bash
set -e

COMMAND=${1:-upgrade}
REVISION=${2:-head}

case "$COMMAND" in
    upgrade)
        echo "⬆️  Upgrading database to: $REVISION"
        uv run alembic upgrade "$REVISION"
        ;;
    downgrade)
        echo "⬇️  Downgrading database to: $REVISION"
        uv run alembic downgrade "$REVISION"
        ;;
    current)
        echo "📍 Current revision:"
        uv run alembic current
        ;;
    history)
        echo "📜 Migration history:"
        uv run alembic history --verbose
        ;;
    generate)
        if [ -z "$2" ]; then
            echo "❌ Error: Migration message required"
            echo "Usage: ./scripts/migrate.sh generate 'add_column_xyz'"
            exit 1
        fi
        echo "🔧 Generating migration: $2"
        uv run alembic revision --autogenerate -m "$2"
        ;;
    heads)
        echo "🔝 Migration heads:"
        uv run alembic heads
        ;;
    check)
        echo "🔍 Checking for pending migrations..."
        uv run alembic check
        ;;
    *)
        echo "Usage: ./scripts/migrate.sh {upgrade|downgrade|current|history|generate|heads|check} [revision]"
        exit 1
        ;;
esac
```

---

### Phase 5: Docker Integration

**Objective**: Run migrations before application startup in containers.

#### Modified Dockerfile

```dockerfile
# ... existing content ...

# 5. Security & Runtime
ENV PATH="/app/.venv/bin:$PATH"

# Creates a non-root user
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# Run migrations then start the application
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop uvloop --log-level info"]
```

#### Alternative: Entrypoint Script

Create `scripts/docker-entrypoint.sh`:

```bash
#!/bin/bash
set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "🚀 Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop uvloop --log-level info
```

Update Dockerfile:

```dockerfile
COPY scripts/docker-entrypoint.sh /app/scripts/
RUN chmod +x /app/scripts/docker-entrypoint.sh
CMD ["/app/scripts/docker-entrypoint.sh"]
```

---

### Phase 6: CI/CD Integration

**Objective**: Validate migrations in CI pipeline.

#### GitHub Actions Example

```yaml
# .github/workflows/migrations.yml
name: Database Migrations

on:
  pull_request:
    paths:
      - 'app/models/**'
      - 'alembic/**'

jobs:
  validate-migrations:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      
      - name: Install dependencies
        run: uv sync --frozen
      
      - name: Run migrations
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
        run: |
          uv run alembic upgrade head
          uv run alembic check
      
      - name: Verify downgrade
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/test
        run: |
          uv run alembic downgrade base
          uv run alembic upgrade head
```

---

## File Summary

### New Files

| File                                     | Description                       |
| ---------------------------------------- | --------------------------------- |
| `alembic.ini`                            | Alembic configuration             |
| `alembic/env.py`                         | Async migration environment       |
| `alembic/script.py.mako`                 | Migration script template         |
| `alembic/README`                         | Alembic readme                    |
| `alembic/versions/`                      | Migration files directory         |
| `alembic/versions/001_initial_schema.py` | Initial schema migration          |
| `scripts/migrate.sh`                     | Migration helper script           |
| `scripts/docker-entrypoint.sh`           | Docker entrypoint with migrations |
| `docs/MIGRATIONS.md`                     | Migration documentation           |

### Modified Files

| File                 | Change                                             |
| -------------------- | -------------------------------------------------- |
| `app/db/database.py` | Remove `create_all()`, add connection verification |
| `Dockerfile`         | Add migration step before app start                |
| `.gitignore`         | Ensure alembic versions are tracked                |
| `pyproject.toml`     | Already has alembic, no change needed              |

---

## Migration Workflow

### Development

```bash
# 1. Make model changes
# 2. Generate migration
uv run alembic revision --autogenerate -m "add_xyz_column"

# 3. Review generated migration (ALWAYS!)
cat alembic/versions/xxx_add_xyz_column.py

# 4. Apply migration locally
uv run alembic upgrade head

# 5. Test downgrade
uv run alembic downgrade -1
uv run alembic upgrade head
```

### Production Deployment

```bash
# 1. Backup database (always!)
pg_dump -h host -U user -d dbname > backup_$(date +%Y%m%d).sql

# 2. Apply migrations
uv run alembic upgrade head

# 3. Verify
uv run alembic current
```

---

## Risk Mitigation

| Risk                       | Mitigation                                                          |
| -------------------------- | ------------------------------------------------------------------- |
| Data loss during migration | Always backup before migrations; test downgrade                     |
| Breaking FK constraints    | Alembic handles FK order automatically; verify in review            |
| Production downtime        | Use `--sql` for offline migrations; apply during maintenance window |
| Schema drift               | Run `alembic check` in CI to detect unapplied migrations            |

---

## Testing Strategy

### Unit Tests

```python
# tests/alembic/test_migrations.py
from alembic import command
from alembic.config import Config

def test_migrations_upgrade_downgrade():
    """Test that all migrations can upgrade and downgrade cleanly."""
    alembic_cfg = Config("alembic.ini")
    
    # Upgrade to head
    command.upgrade(alembic_cfg, "head")
    
    # Downgrade to base
    command.downgrade(alembic_cfg, "base")
    
    # Upgrade again
    command.upgrade(alembic_cfg, "head")
```

---

## Implementation Checklist

- [ ] **Phase 1**: Initialize Alembic (`alembic init alembic`)
- [ ] **Phase 1**: Configure `alembic.ini` with settings
- [ ] **Phase 1**: Create async `env.py` with SQLModel metadata
- [ ] **Phase 2**: Generate initial migration
- [ ] **Phase 2**: Review and test initial migration
- [ ] **Phase 3**: Remove `create_all()` from `init_db()`
- [ ] **Phase 3**: Update startup to verify connection
- [ ] **Phase 4**: Create `scripts/migrate.sh`
- [ ] **Phase 5**: Update Dockerfile with migration step
- [ ] **Phase 5**: Create docker-entrypoint.sh
- [ ] **Phase 6**: Add CI validation workflow
- [ ] **Documentation**: Create `docs/MIGRATIONS.md`
- [ ] **Testing**: Add migration tests

---

## Dependencies

Already installed in `pyproject.toml`:

- `alembic>=1.17.2` ✓
- `sqlmodel>=0.0.27` ✓
- `asyncpg>=0.31.0` ✓

No additional dependencies required.

---

## Estimated Timeline

| Phase                      | Duration     | Dependencies |
| -------------------------- | ------------ | ------------ |
| Phase 1: Setup             | 1 hour       | None         |
| Phase 2: Initial Migration | 1 hour       | Phase 1      |
| Phase 3: App Update        | 30 min       | Phase 2      |
| Phase 4: Scripts           | 30 min       | Phase 2      |
| Phase 5: Docker            | 30 min       | Phase 3      |
| Phase 6: CI/CD             | 1 hour       | Phase 4      |
| Documentation              | 1 hour       | All phases   |
| Testing                    | 1 hour       | All phases   |
| **Total**                  | **~6 hours** |              |

---

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/en/latest/)
- [SQLModel with Alembic](https://sqlmodel.tiangolo.com/tutorial/migrations/)
- [Async Alembic Configuration](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [PostgreSQL JSONB Migrations](https://alembic.sqlalchemy.org/en/latest/dialects.html)

---

*Document Version: 1.0*  
*Last Updated: December 2024*  
*Author: AI Assistant*  
*Status: Ready for Review*
