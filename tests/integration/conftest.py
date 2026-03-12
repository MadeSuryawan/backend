"""Fixtures for repository integration tests."""

from asyncio import run as asyncio_run
from collections.abc import AsyncGenerator
from importlib import import_module

from alembic.config import Config
from pytest import fixture
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from app.db import async_session_maker, engine


async def _reset_schema() -> None:
    """Reset the test schema before Alembic applies migrations."""
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


async def _truncate_tables() -> None:
    """Clear repository tables between tests while keeping migrated schema."""
    await engine.dispose()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE reviews, blogs, users CASCADE"))


@fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Apply the real Alembic schema once for repository integration tests."""
    import_module("app.models")
    asyncio_run(_reset_schema())
    command.upgrade(Config("alembic.ini"), "head")
    asyncio_run(engine.dispose())


@fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Provide a clean async database session backed by the real test Postgres."""
    await _truncate_tables()
    async with async_session_maker() as session:
        yield session
        await session.rollback()
