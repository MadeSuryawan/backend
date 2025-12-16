# tests/idempotency/test_idempotency_manager.py
"""Unit tests for IdempotencyManager."""

from typing import Any

import pytest

from app.errors.idempotency import DuplicateRequestError, IdempotencyStorageError
from app.managers.idempotency_manager import IdempotencyManager
from app.schemas.idempotency import IdempotencyRecord, IdempotencyStatus

pytestmark = pytest.mark.anyio


class TestCheckAndSetProcessing:
    """Tests for check_and_set_processing method."""

    async def test_new_request_returns_none(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """New request should return None and set PROCESSING status."""
        result = await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )
        assert result is None

        # Verify status was set to PROCESSING
        record = await idempotency_manager.get_record(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )
        assert record is not None
        assert record.status == IdempotencyStatus.PROCESSING

    async def test_duplicate_processing_request_raises_error(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Duplicate request while PROCESSING should raise DuplicateRequestError."""
        # First request
        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        # Second request with same key should raise
        with pytest.raises(DuplicateRequestError) as exc_info:
            await idempotency_manager.check_and_set_processing(
                namespace="test",
                idempotency_key=sample_idempotency_key,
            )

        assert sample_idempotency_key in str(exc_info.value)

    async def test_completed_request_returns_record(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
        sample_response: dict[str, Any],
    ) -> None:
        """Completed request should return cached record."""
        # Set up completed record
        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )
        await idempotency_manager.set_completed(
            namespace="test",
            idempotency_key=sample_idempotency_key,
            response=sample_response,
        )

        # Check again - should return cached record
        result = await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        assert result is not None
        assert result.status == IdempotencyStatus.COMPLETED
        assert result.response == sample_response

    async def test_failed_request_allows_retry(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Failed request should allow retry (return None)."""
        # Set up failed record
        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )
        await idempotency_manager.set_failed(
            namespace="test",
            idempotency_key=sample_idempotency_key,
            error="Test error",
        )

        # Check again - should allow retry
        result = await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        assert result is None

        # Status should be PROCESSING again
        record = await idempotency_manager.get_record(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )
        assert record is not None
        assert record.status == IdempotencyStatus.PROCESSING


class TestSetCompleted:
    """Tests for set_completed method."""

    async def test_set_completed_with_response(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
        sample_response: dict[str, Any],
    ) -> None:
        """Should store completed status with response."""
        await idempotency_manager.set_completed(
            namespace="test",
            idempotency_key=sample_idempotency_key,
            response=sample_response,
        )

        record = await idempotency_manager.get_record(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        assert record is not None
        assert record.status == IdempotencyStatus.COMPLETED
        assert record.response == sample_response
        assert record.completed_at is not None


class TestSetFailed:
    """Tests for set_failed method."""

    async def test_set_failed_with_error(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Should store failed status with error message."""
        error_message = "Something went wrong"
        await idempotency_manager.set_failed(
            namespace="test",
            idempotency_key=sample_idempotency_key,
            error=error_message,
        )

        record = await idempotency_manager.get_record(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        assert record is not None
        assert record.status == IdempotencyStatus.FAILED
        assert record.error == error_message
        assert record.completed_at is not None


class TestMetrics:
    """Tests for metrics tracking."""

    async def test_metrics_increment_on_cache_miss(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Cache misses should increment metrics."""
        initial_metrics = idempotency_manager.get_metrics()
        initial_misses = initial_metrics.cache_misses

        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        metrics = idempotency_manager.get_metrics()
        assert metrics.cache_misses == initial_misses + 1

    async def test_metrics_increment_on_cache_hit(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
        sample_response: dict[str, Any],
    ) -> None:
        """Cache hits should increment metrics."""
        # Set up completed record
        await idempotency_manager.set_completed(
            namespace="test",
            idempotency_key=sample_idempotency_key,
            response=sample_response,
        )

        initial_metrics = idempotency_manager.get_metrics()
        initial_hits = initial_metrics.cache_hits

        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        metrics = idempotency_manager.get_metrics()
        assert metrics.cache_hits == initial_hits + 1

    async def test_metrics_increment_on_duplicate_blocked(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Blocked duplicates should increment metrics."""
        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        initial_metrics = idempotency_manager.get_metrics()
        initial_blocked = initial_metrics.duplicate_requests_blocked

        with pytest.raises(DuplicateRequestError):
            await idempotency_manager.check_and_set_processing(
                namespace="test",
                idempotency_key=sample_idempotency_key,
            )

        metrics = idempotency_manager.get_metrics()
        assert metrics.duplicate_requests_blocked == initial_blocked + 1


class TestDeleteOperations:
    """Tests for delete operations."""

    async def test_delete_existing_key(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Deleting existing key should return True."""
        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        result = await idempotency_manager.delete(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        assert result is True

        # Verify it's deleted
        record = await idempotency_manager.get_record(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )
        assert record is None

    async def test_delete_nonexistent_key(
        self,
        idempotency_manager: IdempotencyManager,
    ) -> None:
        """Deleting non-existent key should return False."""
        result = await idempotency_manager.delete(
            namespace="test",
            idempotency_key="nonexistent-key",
        )

        assert result is False


class TestAdminOperations:
    """Tests for admin operations."""

    async def test_delete_key_by_raw_key(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Admin can delete by raw idempotency key."""
        await idempotency_manager.check_and_set_processing(
            namespace="test",
            idempotency_key=sample_idempotency_key,
        )

        # Delete using raw key
        result = await idempotency_manager.delete_key(sample_idempotency_key)
        assert result is True

    async def test_clear_all(
        self,
        idempotency_manager: IdempotencyManager,
    ) -> None:
        """Admin can clear all idempotency records."""
        # Create multiple records
        await idempotency_manager.check_and_set_processing(
            namespace="test1",
            idempotency_key="key1",
        )
        await idempotency_manager.check_and_set_processing(
            namespace="test2",
            idempotency_key="key2",
        )

        # Clear all
        count = await idempotency_manager.clear_all()
        assert count == 2

        # Verify all cleared
        record1 = await idempotency_manager.get_record(
            namespace="test1",
            idempotency_key="key1",
        )
        record2 = await idempotency_manager.get_record(
            namespace="test2",
            idempotency_key="key2",
        )
        assert record1 is None
        assert record2 is None


class TestDifferentNamespaces:
    """Tests for namespace isolation."""

    async def test_same_key_different_namespace(
        self,
        idempotency_manager: IdempotencyManager,
        sample_idempotency_key: str,
    ) -> None:
        """Same key in different namespaces should be independent."""
        # First namespace
        await idempotency_manager.check_and_set_processing(
            namespace="auth:register",
            idempotency_key=sample_idempotency_key,
        )

        # Same key, different namespace - should work
        result = await idempotency_manager.check_and_set_processing(
            namespace="blogs:create",
            idempotency_key=sample_idempotency_key,
        )

        assert result is None


class TestProperties:
    """Tests for manager properties."""

    def test_ttl_property(
        self,
        idempotency_manager: IdempotencyManager,
    ) -> None:
        """TTL property should return configured TTL."""
        assert idempotency_manager.ttl == 3600

    def test_prefix_property(
        self,
        idempotency_manager: IdempotencyManager,
    ) -> None:
        """Prefix property should return configured prefix."""
        assert idempotency_manager.prefix == "test_idempotency"

    def test_reset_metrics(
        self,
        idempotency_manager: IdempotencyManager,
    ) -> None:
        """Reset metrics should clear all counters."""
        idempotency_manager._metrics.cache_hits = 10
        idempotency_manager._metrics.cache_misses = 20

        idempotency_manager.reset_metrics()

        metrics = idempotency_manager.get_metrics()
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
