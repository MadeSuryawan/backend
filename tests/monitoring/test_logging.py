"""Tests for monitoring logging module."""

from app.monitoring.logging import (
    PII_PATTERNS,
    SENSITIVE_HEADERS,
    redact_pii,
    sanitize_headers,
    sanitize_log_message,
)


class TestSanitizeLogMessage:
    """Tests for sanitize_log_message function."""

    def test_removes_newlines(self) -> None:
        """Test that newlines are escaped."""
        message = "Hello\nWorld"
        result = sanitize_log_message(message)
        assert result == "Hello\\nWorld"

    def test_removes_carriage_returns(self) -> None:
        """Test that carriage returns are escaped."""
        message = "Hello\rWorld"
        result = sanitize_log_message(message)
        assert result == "Hello\\rWorld"

    def test_removes_tabs(self) -> None:
        """Test that tabs are escaped."""
        message = "Hello\tWorld"
        result = sanitize_log_message(message)
        assert result == "Hello\\tWorld"

    def test_removes_null_bytes(self) -> None:
        """Test that null bytes are removed."""
        message = "Hello\x00World"
        result = sanitize_log_message(message)
        assert result == "HelloWorld"


class TestSanitizeHeaders:
    """Tests for sanitize_headers function."""

    def test_redacts_sensitive_headers(self) -> None:
        """Test that sensitive headers are redacted."""
        headers = {
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
            "X-API-Key": "secret-key",
        }
        result = sanitize_headers(headers)
        assert result["Authorization"] == "[REDACTED]"
        assert result["Content-Type"] == "application/json"
        assert result["X-API-Key"] == "[REDACTED]"

    def test_case_insensitive_header_matching(self) -> None:
        """Test that header matching is case insensitive."""
        headers = {
            "authorization": "Bearer token123",
            "AUTHORIZATION": "Bearer token456",
        }
        result = sanitize_headers(headers)
        assert result["authorization"] == "[REDACTED]"
        assert result["AUTHORIZATION"] == "[REDACTED]"

    def test_preserves_non_sensitive_headers(self) -> None:
        """Test that non-sensitive headers are preserved."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Test",
        }
        result = sanitize_headers(headers)
        assert result == headers


class TestRedactPII:
    """Tests for redact_pii function."""

    def test_redacts_email(self) -> None:
        """Test that email addresses are redacted."""
        message = "User user@example.com logged in"
        result = redact_pii(message)
        assert "user@example.com" not in result
        assert "[REDACTED_EMAIL]" in result

    def test_redacts_multiple_emails(self) -> None:
        """Test that multiple email addresses are redacted."""
        message = "Users user1@test.com and user2@domain.org"
        result = redact_pii(message)
        assert "user1@test.com" not in result
        assert "user2@domain.org" not in result
        assert result.count("[REDACTED_EMAIL]") == 2

    def test_redacts_phone_number(self) -> None:
        """Test that phone numbers are redacted."""
        message = "Contact +6281234567890"
        result = redact_pii(message)
        assert "+6281234567890" not in result
        assert "[REDACTED_PHONE]" in result

    def test_redacts_credit_card(self) -> None:
        """Test that credit card numbers are redacted."""
        message = "Card 4111-1111-1111-1111"
        result = redact_pii(message)
        assert "4111-1111-1111-1111" not in result
        assert "[REDACTED_CC]" in result

    def test_redacts_ssn(self) -> None:
        """Test that SSN patterns are redacted."""
        message = "SSN 123-45-6789"
        result = redact_pii(message)
        assert "123-45-6789" not in result
        assert "[REDACTED_SSN]" in result

    def test_redacts_jwt_token(self) -> None:
        """Test that JWT tokens are redacted."""
        message = "Token eyJhbGciOiJIUzI1NiIs.eyJzdWIiOiIxMjM0NTY3ODkwIiw.name"
        result = redact_pii(message)
        assert "eyJhbGciOiJIUzI1NiIs" not in result
        assert "[REDACTED_JWT]" in result

    def test_preserves_clean_message(self) -> None:
        """Test that clean messages are preserved."""
        message = "User logged in successfully"
        result = redact_pii(message)
        assert result == message


class TestSensitiveHeadersConstant:
    """Tests for SENSITIVE_HEADERS constant."""

    def test_contains_expected_headers(self) -> None:
        """Test that expected sensitive headers are included."""
        expected = {
            "authorization",
            "cookie",
            "x-api-key",
            "proxy-authorization",
            "x-csrf-token",
            "x-xsrf-token",
        }
        assert expected.issubset(SENSITIVE_HEADERS)


class TestPIIPatterns:
    """Tests for PII patterns."""

    def test_email_pattern_matches_valid_emails(self) -> None:
        """Test that email pattern matches valid email addresses."""
        # Find the email pattern by its replacement text
        email_pattern = None
        for pattern, replacement in PII_PATTERNS:
            if replacement == "[REDACTED_EMAIL]":
                email_pattern = pattern
                break
        assert email_pattern is not None, "Email pattern not found"

        valid_emails = [
            "user@example.com",
            "first.last@domain.co.uk",
            "user+tag@example.org",
        ]
        for email in valid_emails:
            assert email_pattern.search(email), f"Should match: {email}"

    def test_email_pattern_does_not_match_invalid(self) -> None:
        """Test that email pattern doesn't match invalid strings."""
        # Find the email pattern by its replacement text
        email_pattern = None
        for pattern, replacement in PII_PATTERNS:
            if replacement == "[REDACTED_EMAIL]":
                email_pattern = pattern
                break
        assert email_pattern is not None, "Email pattern not found"

        invalid = [
            "not-an-email",
            "@nodomain.com",
            "noat.com",
        ]
        for text in invalid:
            assert not email_pattern.search(text), f"Should not match: {text}"
