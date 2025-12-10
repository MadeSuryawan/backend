from collections.abc import Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# CORRECTED IMPORTS: Point to the new location inside 'app'
from app import app
from app.clients.email_client import EmailClient
from app.managers import limiter
from app.routes.ai import get_email_client as ai_get_email_client
from app.routes.email import get_email_client as email_get_email_client


@pytest.fixture
def mock_email_client() -> Generator[MagicMock]:
    mock_client = MagicMock(spec=EmailClient)
    mock_client.send_email.return_value = {"id": "mock_msg_123", "threadId": "mock_thread_123"}
    yield mock_client


@pytest.fixture
def client(mock_email_client: MagicMock) -> Generator[TestClient]:
    # Disable rate limiting for tests
    limiter.enabled = False
    app.dependency_overrides[email_get_email_client] = lambda: mock_email_client
    app.dependency_overrides[ai_get_email_client] = lambda: mock_email_client
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    # Re-enable rate limiter after test
    limiter.enabled = True
