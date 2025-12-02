"""Tests for app/schemas/email.py."""

import pytest
from pydantic import ValidationError

from app.schemas.email import DISPOSABLE_DOMAINS, EmailRequest, EmailResponse


class TestEmailRequest:
    """Tests for EmailRequest schema validation."""

    def test_valid_email_request(self) -> None:
        """Test valid email request passes validation."""
        request = EmailRequest(
            subject="Test Subject",
            message="Test message body",
            email="user@gmail.com",
        )
        assert request.subject == "Test Subject"
        assert request.message == "Test message body"
        assert request.email == "user@gmail.com"

    def test_empty_subject_fails(self) -> None:
        """Test that empty subject fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            EmailRequest(subject="", message="Test message", email="user@gmail.com")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("subject",) for e in errors)

    def test_empty_message_fails(self) -> None:
        """Test that empty message fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            EmailRequest(subject="Subject", message="", email="user@gmail.com")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("message",) for e in errors)

    def test_invalid_email_format_fails(self) -> None:
        """Test that invalid email format fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            EmailRequest(subject="Subject", message="Message", email="not-an-email")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("email",) for e in errors)

    def test_email_without_at_sign_fails(self) -> None:
        """Test that email without @ sign fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            EmailRequest(subject="Subject", message="Message", email="usergmail.com")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("email",) for e in errors)

    @pytest.mark.parametrize("disposable_domain", DISPOSABLE_DOMAINS[:5])
    def test_disposable_email_domains_rejected(self, disposable_domain: str) -> None:
        """Test that known disposable email domains are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            EmailRequest(
                subject="Test",
                message="Message",
                email=f"user@{disposable_domain}",
            )
        errors = exc_info.value.errors()
        assert any("temporary mail service" in str(e.get("msg", "")) for e in errors)

    def test_valid_email_domains_accepted(self) -> None:
        """Test that valid email domains are accepted."""
        valid_domains = ["gmail.com", "yahoo.com", "outlook.com", "company.org"]
        for domain in valid_domains:
            request = EmailRequest(
                subject="Test",
                message="Message",
                email=f"user@{domain}",
            )
            assert request.email == f"user@{domain}"

    def test_email_case_insensitive_domain_check(self) -> None:
        """Test that domain check is case-insensitive."""
        # MAILINATOR.COM should still be blocked
        with pytest.raises(ValidationError):
            EmailRequest(
                subject="Test",
                message="Message",
                email="user@MAILINATOR.COM",
            )

    def test_non_string_email_raises_type_error(self) -> None:
        """Test that non-string email raises TypeError or ValidationError."""
        with pytest.raises(TypeError):
            EmailRequest(
                subject="Test",
                message="Message",
                email=12345,
            )


class TestEmailResponse:
    """Tests for EmailResponse schema."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        response = EmailResponse()
        assert response.status == "success"
        assert response.message == "Email sent successfully"

    def test_custom_values(self) -> None:
        """Test custom values override defaults."""
        response = EmailResponse(status="error", message="Failed to send email")
        assert response.status == "error"
        assert response.message == "Failed to send email"

    def test_model_serialization(self) -> None:
        """Test model serializes correctly."""
        response = EmailResponse()
        data = response.model_dump()
        assert data["status"] == "success"
        assert data["message"] == "Email sent successfully"


class TestDisposableDomains:
    """Tests for DISPOSABLE_DOMAINS constant."""

    def test_disposable_domains_is_list(self) -> None:
        """Test that DISPOSABLE_DOMAINS is a list."""
        assert isinstance(DISPOSABLE_DOMAINS, list)

    def test_disposable_domains_not_empty(self) -> None:
        """Test that DISPOSABLE_DOMAINS is not empty."""
        assert len(DISPOSABLE_DOMAINS) > 0

    def test_known_disposable_domains_included(self) -> None:
        """Test that known disposable domains are in the list."""
        known_domains = ["mailinator.com", "yopmail.com", "10minutemail.com"]
        for domain in known_domains:
            assert domain in DISPOSABLE_DOMAINS
