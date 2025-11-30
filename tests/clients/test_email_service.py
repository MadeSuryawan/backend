from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.clients.email_client import EmailClient
from app.errors import ConfigurationError


def test_email_client_initialization_no_token() -> None:
    """Test that missing token raises ConfigurationError."""
    # We patch Path.exists to return False to simulate missing token.json
    with patch("pathlib.Path.exists", return_value=False):
        client = EmailClient()

        # Expect ConfigurationError instead of FileNotFoundError
        with pytest.raises(ConfigurationError):
            _ = client.service


def test_create_message_format() -> None:
    client = EmailClient()
    # Added reply_to argument here
    result = client._create_message(
        subject="Test",
        body="Body",
        sender="me",
        to="test@example.com",
        reply_to="user@example.com",
    )
    assert "raw" in result


def test_contact_support_endpoint_success(client: TestClient, mock_email_client: MagicMock) -> None:
    # Added 'email' to payload
    payload = {"subject": "Help", "message": "Please help.", "email": "user@test.com"}
    response = client.post("/email/contact-support/", json=payload)
    assert response.status_code == 200
    mock_email_client.send_email.assert_called_once()


def test_contact_background_endpoint(client: TestClient, mock_email_client: MagicMock) -> None:
    # Added 'email' to payload
    payload = {"subject": "Bg", "message": "Bg msg.", "email": "user@test.com"}
    response = client.post("/email/contact-background/", json=payload)
    assert response.status_code == 200
    mock_email_client.send_email.assert_called_once()
