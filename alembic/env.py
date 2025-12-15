"""
Alembic migration environment configuration for async SQLModel.

This module configures Alembic to work with:
- Async PostgreSQL via asyncpg
- SQLModel metadata for autogenerate support
- Application settings for database URL
"""

from asyncio import run as asyncio_run
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context
from app.configs import settings

# Import all models to register them with SQLModel.metadata
# This is required for autogenerate to detect model changes
from app.models import BlogDB, UserDB  # noqa: F401

# Alembic Config object - provides access to .ini file values
config = context.config

# Override sqlalchemy.url with actual database URL from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Configure Python logging from .ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLModel metadata for autogenerate support
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This generates SQL script output without connecting to the database.
    Useful for generating migration scripts to be reviewed or applied manually.

    The context is configured with:
    - literal_binds: Renders bound parameters inline in SQL
    - compare_type: Detects column type changes
    - compare_server_default: Detects server default changes
    """
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
    """
    Execute migrations with the given database connection.

    Args:
        connection: SQLAlchemy database connection
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    This connects to the database and runs migrations directly.
    Uses async engine for compatibility with asyncpg driver.
    """
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
