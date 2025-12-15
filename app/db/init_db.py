"""
Database initialization and verification script.

This script verifies database connectivity and can be run independently
or as part of the application startup.

Note:
    Database schema is managed by Alembic migrations.
    Run 'uv run alembic upgrade head' to apply migrations.
"""

from asyncio import run as asyncio_run
from logging import getLogger

from app.db.database import init_db
from app.errors.database import DatabaseInitializationError
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


async def main() -> None:
    """Verify database connection."""
    try:
        logger.info("Verifying database connection...")
        await init_db()
        logger.info("Database ready!")
    except Exception as e:
        logger.exception("Failed to connect to database")
        raise DatabaseInitializationError from e


if __name__ == "__main__":
    asyncio_run(main())
