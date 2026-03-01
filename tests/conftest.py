# tests/conftest.py
"""Root pytest configuration and shared fixtures."""

from atexit import register
from os import environ

# ---------------------------------------------------------------------------
# PostgreSQL testcontainer — must be configured BEFORE any app module import.
#
# app/db/database.py creates the SQLAlchemy async engine at *module-import
# time* using settings.DATABASE_URL.  Pydantic-Settings resolves env vars at
# instantiation time, so we must set DATABASE_URL in the environment before
# the app package is first imported (which happens during pytest collection).
#
# Solution: start a throwaway PostgreSQL Docker container here, derive its
# connection URL, and write it into os.environ.  The container is stopped
# automatically via atexit when the pytest process exits.
#
# Requirements: Docker must be running (the same Docker daemon used by
# docker-compose for the dev server is sufficient).  No desktop PostgreSQL
# app or pre-started docker-compose services are needed for tests.
# ---------------------------------------------------------------------------
from testcontainers.postgres import PostgresContainer as _PostgresContainer

_pg = _PostgresContainer("postgres:15-alpine")
_pg.start()

# testcontainers returns a psycopg2 URL; the app requires asyncpg.
_raw_pg_url: str = _pg.get_connection_url()
_asyncpg_url = _raw_pg_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
    "postgresql://",
    "postgresql+asyncpg://",
)

environ["DATABASE_URL"] = _asyncpg_url

# Stop the container when the test process exits (works for both normal exit
# and KeyboardInterrupt; pytest's own teardown runs before atexit handlers).
register(_pg.stop)

# Ensure test host is included in trusted hosts for all tests
# This must happen before app is imported anywhere
_TEST_TRUSTED_HOSTS = "localhost,127.0.0.1,0.0.0.0,host.docker.internal,testserver,test"
environ["TRUSTED_HOSTS"] = _TEST_TRUSTED_HOSTS
