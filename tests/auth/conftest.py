"""Pytest configuration and fixtures for authentication tests."""

from collections.abc import AsyncGenerator
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from pytest import fixture

from app.clients.redis_client import RedisClient
from app.main import app
from app.managers.login_attempt_tracker import LoginAttemptTracker
from app.managers.rate_limiter import limiter
from app.managers.token_blacklist import TokenBlacklist
from app.managers.token_manager import create_access_token, create_refresh_token
from app.models import UserDB


@fixture
def mock_redis_client() -> MagicMock:
    """Create a mock Redis client for testing."""
    mock = MagicMock(spec=RedisClient)
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.exists = AsyncMock(return_value=0)
    mock.ttl = AsyncMock(return_value=-2)
    mock.scan_iter = AsyncMock(return_value=iter([]))
    return mock


@fixture
def token_blacklist(mock_redis_client: MagicMock) -> TokenBlacklist:
    """Create a token blacklist with mocked Redis."""
    return TokenBlacklist(mock_redis_client)


@fixture
def login_tracker(mock_redis_client: MagicMock) -> LoginAttemptTracker:
    """Create a login attempt tracker with mocked Redis."""
    return LoginAttemptTracker(mock_redis_client)


@fixture
def sample_user() -> UserDB:
    """Create a sample user for testing."""
    return UserDB(
        uuid=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$somehash",
        is_active=True,
        is_verified=True,
        role="user",
        first_name="Test",
        last_name="User",
    )


@fixture
def admin_user() -> UserDB:
    """Create an admin user for testing."""
    return UserDB(
        uuid=uuid4(),
        username="adminuser",
        email="admin@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$somehash",
        is_active=True,
        is_verified=True,
        role="admin",
        first_name="Admin",
        last_name="User",
    )


@fixture
def unverified_user() -> UserDB:
    """Create an unverified user for testing."""
    return UserDB(
        uuid=uuid4(),
        username="unverified",
        email="unverified@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$somehash",
        is_active=True,
        is_verified=False,
        role="user",
        first_name="Unverified",
        last_name="User",
    )


@fixture
def sample_access_token(sample_user: UserDB) -> str:
    """Create a sample access token for testing."""
    return create_access_token(
        user_id=sample_user.uuid,
        username=sample_user.username,
        expires_delta=timedelta(minutes=30),
    )


@fixture
def sample_refresh_token(sample_user: UserDB) -> str:
    """Create a sample refresh token for testing."""
    return create_refresh_token(
        user_id=sample_user.uuid,
        username=sample_user.username,
        expires_delta=timedelta(days=7),
    )


@fixture
def expired_access_token(sample_user: UserDB) -> str:
    """Create an expired access token for testing."""
    return create_access_token(
        user_id=sample_user.uuid,
        username=sample_user.username,
        expires_delta=timedelta(seconds=-1),  # Already expired
    )


@fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async HTTP client for testing auth endpoints."""
    limiter.enabled = False
    async with AsyncClient(
        base_url="http://test",
        transport=ASGITransport(app=app),
    ) as ac:
        yield ac


@fixture
def auth_headers(sample_access_token: str) -> dict[str, str]:
    """Create auth headers with a valid access token."""
    return {"Authorization": f"Bearer {sample_access_token}"}
