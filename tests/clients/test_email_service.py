from base64 import urlsafe_b64decode
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError

from app.clients.email_client import _HEADER_INJECTION_PATTERN, EmailClient
from app.errors import AuthenticationError, ConfigurationError, SendingError


class TestEmailClientValidation:
    """Tests for email validation and sanitization."""

    def test_validate_email_returns_me_as_is(self) -> None:
        """Test that 'me' special value is returned as-is."""
        client = EmailClient()
        result = client._validate_email("me")
        assert result == "me"

    def test_validate_email_valid_address(self) -> None:
        """Test validation of a valid email address."""
        client = EmailClient()
        result = client._validate_email("user@example.com")
        assert result == "user@example.com"

    def test_validate_email_with_header_injection_newline(self) -> None:
        """Test that newline characters in email are rejected."""
        client = EmailClient()
        with pytest.raises(ValueError, match="header injection"):
            client._validate_email("user@example.com\nBcc: attacker@evil.com")

    def test_validate_email_with_header_injection_carriage_return(self) -> None:
        """Test that carriage return characters in email are rejected."""
        client = EmailClient()
        with pytest.raises(ValueError, match="header injection"):
            client._validate_email("user@example.com\rBcc: attacker@evil.com")

    def test_validate_email_invalid_format_no_at(self) -> None:
        """Test that email without @ is rejected."""
        client = EmailClient()
        with pytest.raises(ValueError, match="Invalid email address"):
            client._validate_email("invalid-email")

    def test_sanitize_header_removes_newlines(self) -> None:
        """Test that header sanitization removes newlines."""
        client = EmailClient()
        result = client._sanitize_header("Subject\nInjected Header: value")
        assert "\n" not in result
        assert result == "SubjectInjected Header: value"

    def test_sanitize_header_removes_carriage_returns(self) -> None:
        """Test that header sanitization removes carriage returns."""
        client = EmailClient()
        result = client._sanitize_header("Subject\rInjected: value")
        assert "\r" not in result

    def test_header_injection_pattern_matches_newlines(self) -> None:
        """Test that the regex pattern matches newlines and carriage returns."""
        assert _HEADER_INJECTION_PATTERN.search("test\nvalue")
        assert _HEADER_INJECTION_PATTERN.search("test\rvalue")
        assert not _HEADER_INJECTION_PATTERN.search("test value")


class TestEmailClientInitialization:
    """Tests for EmailClient initialization."""

    def test_email_client_initialization_no_token(self) -> None:
        """Test that missing token raises ConfigurationError."""
        with patch("pathlib.Path.exists", return_value=False):
            client = EmailClient()
            with pytest.raises(ConfigurationError):
                _ = client.service

    def test_email_client_init_attributes(self) -> None:
        """Test that EmailClient initializes with correct attributes."""
        client = EmailClient()
        assert client._credentials is None
        assert client._service is None
        assert client._service_lock is not None


class TestCreateMessage:
    """Tests for _create_message method."""

    def test_create_message_format(self) -> None:
        """Test message creation returns proper format."""
        client = EmailClient()
        result = client._create_message(
            subject="Test Subject",
            body="Test Body",
            sender="me",
            to="recipient@example.com",
            reply_to="sender@example.com",
        )
        assert "raw" in result
        assert isinstance(result["raw"], str)

    def test_create_message_encoded_content(self) -> None:
        """Test that message content is properly base64 encoded."""
        client = EmailClient()
        result = client._create_message(
            subject="Test",
            body="Hello World",
            sender="me",
            to="test@example.com",
            reply_to="user@example.com",
        )
        # Decode and verify content
        decoded = urlsafe_b64decode(result["raw"]).decode("utf-8")
        assert "Hello World" in decoded
        assert "Subject: Test" in decoded

    def test_create_message_sanitizes_subject(self) -> None:
        """Test that subject is sanitized."""
        client = EmailClient()
        result = client._create_message(
            subject="Test\nInjected",
            body="Body",
            sender="me",
            to="test@example.com",
            reply_to="user@example.com",
        )
        decoded = urlsafe_b64decode(result["raw"]).decode("utf-8")
        assert "Subject: TestInjected" in decoded


class TestGetCredentials:
    """Tests for _get_credentials method."""

    @patch("pathlib.Path.exists", return_value=False)
    def test_get_credentials_no_token_file(self, mock_exists: MagicMock) -> None:  # noqa: ARG002
        """Test ConfigurationError when token file doesn't exist."""
        client = EmailClient()
        with pytest.raises(ConfigurationError, match="Valid token not found"):
            client._get_credentials()

    @patch("pathlib.Path.exists", return_value=True)
    @patch("google.oauth2.credentials.Credentials.from_authorized_user_file")
    def test_get_credentials_corrupt_token(
        self,
        mock_creds: MagicMock,
        mock_exists: MagicMock,  # noqa: ARG002
    ) -> None:
        """Test AuthenticationError when token file is corrupt."""
        mock_creds.side_effect = ValueError("Invalid token")
        client = EmailClient()
        with pytest.raises(AuthenticationError, match="Token file is corrupt"):
            client._get_credentials()


class TestSendSync:
    """Tests for send_sync method."""

    def test_send_sync_http_error(self) -> None:
        """Test SendingError on HttpError."""
        client = EmailClient()

        # Create a mock service that raises HttpError
        mock_service = MagicMock()
        mock_execute = MagicMock(
            side_effect=HttpError(resp=MagicMock(status=400), content=b"Bad Request"),
        )
        mock_service.users.return_value.messages.return_value.send.return_value.execute = (
            mock_execute
        )
        client._service = mock_service

        with pytest.raises(SendingError, match="Google API refused request"):
            client.send_sync("Subject", "Body", "reply@example.com")

    def test_send_sync_unexpected_error(self) -> None:
        """Test SendingError on unexpected error."""
        client = EmailClient()

        # Create a mock service that raises an unexpected error
        mock_service = MagicMock()
        mock_execute = MagicMock(side_effect=RuntimeError("Unexpected"))
        mock_service.users.return_value.messages.return_value.send.return_value.execute = (
            mock_execute
        )
        client._service = mock_service

        with pytest.raises(SendingError, match="unexpected internal error"):
            client.send_sync("Subject", "Body", "reply@example.com")


class TestEndpoints:
    """Tests for email endpoints."""

    def test_contact_support_endpoint_success(
        self,
        client: TestClient,
        mock_email_client: MagicMock,
    ) -> None:
        """Test successful contact support endpoint."""
        payload = {"subject": "Help", "message": "Please help.", "email": "user@test.com"}
        response = client.post("/email/contact-support/", json=payload)
        assert response.status_code == 200
        mock_email_client.send_email.assert_called_once()

    def test_contact_background_endpoint(
        self,
        client: TestClient,
        mock_email_client: MagicMock,
    ) -> None:
        """Test contact background endpoint."""
        payload = {"subject": "Bg", "message": "Bg msg.", "email": "user@test.com"}
        response = client.post("/email/contact-background/", json=payload)
        assert response.status_code == 200
        mock_email_client.send_email.assert_called_once()
