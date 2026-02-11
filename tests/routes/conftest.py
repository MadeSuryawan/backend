# tests/routes/conftest.py
"""Pytest fixtures for route tests."""

from collections.abc import AsyncGenerator
from datetime import timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.main import app
from app.managers.rate_limiter import limiter
from app.managers.token_manager import create_access_token
from app.models import UserDB


@pytest.fixture
def sample_user() -> UserDB:
    """Create a sample user for testing."""
    return UserDB(
        uuid=uuid4(),
        username="testuser",
        email="test@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$somehash",
        is_verified=True,
        role="user",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def admin_user() -> UserDB:
    """Create an admin user for testing."""
    return UserDB(
        uuid=uuid4(),
        username="adminuser",
        email="admin@example.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$somehash",
        is_verified=True,
        role="admin",
        first_name="Admin",
        last_name="User",
    )


@pytest.fixture
def sample_access_token(sample_user: UserDB) -> str:
    """Create a sample access token for testing."""
    return create_access_token(
        user_id=sample_user.uuid,
        username=sample_user.username,
        expires_delta=timedelta(minutes=30),
    )


@pytest.fixture
def admin_access_token(admin_user: UserDB) -> str:
    """Create an admin access token for testing."""
    return create_access_token(
        user_id=admin_user.uuid,
        username=admin_user.username,
        expires_delta=timedelta(minutes=30),
    )


@pytest.fixture
def auth_headers(sample_access_token: str) -> dict[str, str]:
    """Create auth headers with a valid access token."""
    return {"Authorization": f"Bearer {sample_access_token}"}


@pytest.fixture
def admin_auth_headers(admin_access_token: str) -> dict[str, str]:
    """Create auth headers with an admin access token."""
    return {"Authorization": f"Bearer {admin_access_token}"}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async HTTP client for testing."""
    limiter.enabled = False
    async with AsyncClient(
        base_url="http://test",
        transport=ASGITransport(app=app),
    ) as ac:
        yield ac
    limiter.enabled = True


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    """Create valid JPEG image bytes."""
    img = Image.new("RGB", (200, 200), color="red")
    buffer = BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def valid_png_bytes() -> bytes:
    """Create valid PNG image bytes."""
    img = Image.new("RGBA", (200, 200), color="blue")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def mock_user_repo(sample_user: UserDB) -> MagicMock:
    """Create a mock user repository."""
    mock = MagicMock()
    mock.get_by_id = AsyncMock(return_value=sample_user)
    mock.update = AsyncMock(return_value=sample_user)
    return mock


@pytest.fixture
def mock_cache_manager() -> MagicMock:
    """Create a mock cache manager."""
    mock = MagicMock()
    mock.delete = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    return mock
