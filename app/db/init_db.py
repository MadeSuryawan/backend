"""
Database initialization script.

This script creates all database tables and can be run independently
or as part of the application startup.
"""

from asyncio import run as asyncio_run
from logging import getLogger

from app.configs import file_logger
from app.db.database import init_db
from app.errors.database import DatabaseInitializationError

logger = file_logger(getLogger(__name__))


async def main() -> None:
    """Initialize database tables."""
    try:
        logger.info("Creating database tables...")
        await init_db()
    except Exception as e:
        logger.exception("Failed to initialize database")
        raise DatabaseInitializationError from e


if __name__ == "__main__":
    asyncio_run(main())
