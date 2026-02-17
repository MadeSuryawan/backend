"""Tests for structured logging functionality."""

from __future__ import annotations

import pytest

from app.monitoring.logging import (
    get_request_id,
    mask_ip,
    redact_pii,
    redact_sensitive_value,
    sanitize_event_dict,
    sanitize_headers,
    sanitize_log_message,
    set_client_ip,
    set_request_id,
    set_user_id,
)


class TestSanitizeLogMessage:
    """Tests for log message sanitization."""

    def test_newlines_escaped(self) -> None:
        """Newlines should be escaped to prevent log injection."""
        message = "Line1\nLine2\rLine3"
        result = sanitize_log_message(message)
        assert "\\n" in result
        assert "\\r" in result
        assert "\n" not in result
        assert "\r" not in result

    def test_normal_message_unchanged(self) -> None:
        """Normal messages should be unchanged."""
        message = "User logged in successfully"
        assert sanitize_log_message(message) == message

    def test_non_string_converted(self) -> None:
        """Non-string values should be converted to string."""
        assert sanitize_log_message(123) == "123"  # type: ignore[arg-type]


class TestSanitizeHeaders:
    """Tests for HTTP header sanitization."""

    def test_authorization_redacted(self) -> None:
        """Authorization header should be redacted."""
        headers = {"Authorization": "Bearer secret-token"}
        result = sanitize_headers(headers)
        assert result["Authorization"] == "[REDACTED]"

    def test_cookie_redacted(self) -> None:
        """Cookie header should be redacted."""
        headers = {"Cookie": "session=abc123"}
        result = sanitize_headers(headers)
        assert result["Cookie"] == "[REDACTED]"

    def test_api_key_redacted(self) -> None:
        """X-API-Key header should be redacted."""
        headers = {"X-API-Key": "my-secret-key"}
        result = sanitize_headers(headers)
        assert result["X-API-Key"] == "[REDACTED]"

    def test_normal_headers_unchanged(self) -> None:
        """Normal headers should be unchanged."""
        headers = {"Content-Type": "application/json", "Accept": "*/*"}
        result = sanitize_headers(headers)
        assert result == headers


class TestRedactPII:
    """Tests for PII redaction."""

    def test_email_redacted(self) -> None:
        """Email addresses should be redacted."""
        text = "User email is user@example.com"
        result = redact_pii(text)
        assert "user@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_phone_redacted(self) -> None:
        """Phone numbers should be redacted."""
        text = "Call me at 555-123-4567"
        result = redact_pii(text)
        assert "555-123-4567" not in result
        assert "[REDACTED_PHONE]" in result

    def test_normal_text_unchanged(self) -> None:
        """Normal text without PII should be unchanged."""
        text = "User completed the task"
        assert redact_pii(text) == text


class TestRedactSensitiveValue:
    """Tests for sensitive field redaction."""

    def test_password_field_redacted(self) -> None:
        """Password fields should be redacted."""
        assert redact_sensitive_value("password", "secret123") == "[REDACTED]"
        assert redact_sensitive_value("user_password", "secret123") == "[REDACTED]"

    def test_token_field_redacted(self) -> None:
        """Token fields should be redacted."""
        assert redact_sensitive_value("access_token", "abc123") == "[REDACTED]"
        assert redact_sensitive_value("api_key", "key123") == "[REDACTED]"

    def test_normal_field_unchanged(self) -> None:
        """Normal fields should be unchanged."""
        assert redact_sensitive_value("username", "john") == "john"


class TestSanitizeEventDict:
    """Tests for event dictionary sanitization."""

    def test_nested_sensitive_fields_redacted(self) -> None:
        """Nested sensitive fields should be redacted."""
        event = {
            "user": {
                "username": "john",
                "password": "secret123",
            },
        }
        result = sanitize_event_dict(event)
        assert result["user"]["username"] == "john"
        assert result["user"]["password"] == "[REDACTED]"

    def test_list_values_sanitized(self) -> None:
        """List values should be sanitized."""
        event = {
            "tokens": ["token1", "token2"],
        }
        result = sanitize_event_dict(event)
        assert isinstance(result["tokens"], list)


class TestContextVariables:
    """Tests for context variable management."""

    def test_set_and_get_request_id(self) -> None:
        """Request ID should be set and retrieved correctly."""
        set_request_id("req-123")
        assert get_request_id() == "req-123"
        set_request_id(None)
        assert get_request_id() is None

    def test_set_user_id(self) -> None:
        """User ID should be set without error."""
        set_user_id("user-123")
        set_user_id(None)

    def test_set_client_ip(self) -> None:
        """Client IP should be set without error."""
        set_client_ip("192.168.1.1")
        set_client_ip(None)


class TestMaskIP:
    """Tests for IP address masking."""

    def test_ipv4_masked(self) -> None:
        """IPv4 addresses should be partially masked."""
        assert mask_ip("192.168.1.100") == "192.168.xxx.xxx"

    def test_invalid_ip_fully_masked(self) -> None:
        """Invalid IPs should be fully masked."""
        assert mask_ip("invalid") == "xxx.xxx.xxx.xxx"
