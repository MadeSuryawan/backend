"""Database engine and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from logging import getLogger

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.configs import file_logger, settings

logger = file_logger(getLogger(__name__))

STATEMENT_TIMEOUT_MS = 30000


def _configure_engine_events(engine: AsyncEngine) -> None:
    """Configure connection pool events for monitoring."""

    @event.listens_for(engine.sync_engine, "connect")
    def on_connect(dbapi_connection: object, connection_record: object) -> None:
        logger.debug("New database connection established")

    @event.listens_for(engine.sync_engine, "checkout")
    def on_checkout(
        dbapi_connection: object,
        connection_record: object,
        connection_proxy: object,
    ) -> None:
        logger.debug("Connection checked out from pool")

    @event.listens_for(engine.sync_engine, "checkin")
    def on_checkin(dbapi_connection: object, connection_record: object) -> None:
        logger.debug("Connection returned to pool")


engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.MAX_OVERFLOW,
    pool_timeout=settings.POOL_TIMEOUT,
    pool_recycle=settings.POOL_RECYCLE,
    pool_pre_ping=True,
    connect_args={
        "command_timeout": STATEMENT_TIMEOUT_MS / 1000,
        "server_settings": {
            "statement_timeout": str(STATEMENT_TIMEOUT_MS),
            "lock_timeout": str(STATEMENT_TIMEOUT_MS),
        },
    },
)

if settings.DEBUG:
    _configure_engine_events(engine)

async_session_maker: async_sessionmaker[SQLModelAsyncSession] = async_sessionmaker(
    engine,
    class_=SQLModelAsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """
    Dependency for getting async database sessions.

    This function is used as a FastAPI dependency to provide
    database sessions to route handlers.

    Yields:
        AsyncSession: Database session

    Example:
        ```python
        @app.get("/users")
        async def get_users(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(UserDB))
            return result.scalars().all()
        ```
    """
    async with transaction() as session:
        yield session


@asynccontextmanager
async def transaction() -> AsyncGenerator[AsyncSession]:
    """
    Context manager for explicit transaction management.

    Use this for operations that need explicit transaction control.

    Yields:
        AsyncSession: Database session within a transaction

    Example:
        ```python
        async with transaction() as session:
            user = UserDB(username="test", ...)
            session.add(user)
            # Commits on successful exit, rolls back on exception
        ```
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Transaction error")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.

    This function creates all tables defined in SQLModel models.
    It should be called on application startup.

    Note:
        This is a simple initialization for development.
        For production, use proper migration tools like Alembic.
    """
    async with engine.begin() as conn:
        # Import all models to ensure they are registered
        from app.models import BlogDB, UserDB  # noqa: F401, PLC0415

        # Create all tables
        await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database initialized successfully!")


async def close_db() -> None:
    """
    Close database connections.

    This function should be called on application shutdown
    to properly close all database connections.
    """
    await engine.dispose()
    logger.info("Database connections closed")
