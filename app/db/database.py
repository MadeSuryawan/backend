"""Database engine and session management."""

from collections.abc import AsyncGenerator
from logging import getLogger

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


# Create async engine with connection pooling
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.POOL_SIZE,
    max_overflow=settings.MAX_OVERFLOW,
    pool_timeout=settings.POOL_TIMEOUT,
    pool_recycle=settings.POOL_RECYCLE,
    pool_pre_ping=True,  # Verify connections before using them
)

# Create async session factory
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
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
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
