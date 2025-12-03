"""
Database initialization script.

This script creates all database tables and can be run independently
or as part of the application startup.
"""

from asyncio import run as asyncio_run
from logging import getLogger

from app.configs import file_logger
from app.db.database import init_db

logger = file_logger(getLogger(__name__))


async def main() -> None:
    """Initialize database tables."""
    logger.info("Creating database tables...")
    await init_db()
    logger.info("Database tables created successfully!")


if __name__ == "__main__":
    asyncio_run(main())
