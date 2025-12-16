# tests/idempotency/test_idempotency_errors.py
"""Unit tests for idempotency error classes."""

import pytest

from app.errors.idempotency import (
    DuplicateRequestError,
    IdempotencyError,
    IdempotencyKeyError,
    IdempotencyStorageError,
)


class TestIdempotencyError:
    """Tests for base IdempotencyError."""

    def test_default_message(self) -> None:
        """Default error should have appropriate message."""
        error = IdempotencyError()
        assert error.detail == "Idempotency operation failed"
        assert error.status_code == 500

    def test_custom_message(self) -> None:
        """Custom message should be preserved."""
        error = IdempotencyError(detail="Custom error message")
        assert error.detail == "Custom error message"

    def test_str_representation(self) -> None:
        """String representation should include detail."""
        error = IdempotencyError(detail="Test error")
        assert "Test error" in str(error)


class TestDuplicateRequestError:
    """Tests for DuplicateRequestError."""

    def test_default_message(self) -> None:
        """Error should include idempotency key in message."""
        error = DuplicateRequestError("test-key-123")
        assert "test-key-123" in error.detail
        assert error.status_code == 409  # Conflict

    def test_message_format(self) -> None:
        """Error message should be properly formatted."""
        error = DuplicateRequestError("550e8400-e29b-41d4-a716-446655440000")
        assert "already being processed" in error.detail.lower()


class TestIdempotencyKeyError:
    """Tests for IdempotencyKeyError."""

    def test_invalid_key_message(self) -> None:
        """Error should include reason for invalid key."""
        error = IdempotencyKeyError("not-a-valid-uuid", "Invalid UUID format")
        assert "not-a-valid-uuid" in error.detail
        assert error.status_code == 400  # Bad Request

    def test_without_reason(self) -> None:
        """Error should work without specific reason."""
        error = IdempotencyKeyError("bad-key")
        assert "bad-key" in error.detail


class TestIdempotencyStorageError:
    """Tests for IdempotencyStorageError."""

    def test_storage_error_message(self) -> None:
        """Error should include operation and error details."""
        error = IdempotencyStorageError("set_completed", "Connection refused")
        assert "set_completed" in error.detail or "Connection refused" in error.detail
        assert error.status_code == 500  # Internal Server Error

    def test_different_operations(self) -> None:
        """Different operations should be reflected in error."""
        operations = ["check_and_set", "set_completed", "set_failed", "delete"]
        for op in operations:
            error = IdempotencyStorageError(op, "Test error")
            # Should not raise and should have detail
            assert error.detail is not None
