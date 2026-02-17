"""Tests for Prometheus metrics functionality."""

from __future__ import annotations

import pytest

from app.monitoring.prometheus import (
    normalize_path,
    record_ai_request,
    record_cache_hit,
    record_cache_miss,
    record_cache_operation,
    record_circuit_breaker_failure,
    record_circuit_breaker_success,
    record_rate_limit_hit,
    sanitize_label_value,
    set_circuit_breaker_state,
)


class TestSanitizeLabelValue:
    """Tests for label value sanitization."""

    def test_empty_value_returns_unknown(self) -> None:
        """Empty values should return 'unknown'."""
        assert sanitize_label_value("") == "unknown"

    def test_normal_value_unchanged(self) -> None:
        """Normal values should be unchanged."""
        assert sanitize_label_value("users") == "users"

    def test_long_value_truncated(self) -> None:
        """Long values should be truncated."""
        long_value = "a" * 2000
        result = sanitize_label_value(long_value)
        assert len(result) == 1024


class TestNormalizePath:
    """Tests for path normalization to prevent high cardinality."""

    def test_numeric_id_replaced(self) -> None:
        """Numeric IDs in paths should be replaced."""
        assert normalize_path("/users/123") == "/users/{id}"
        assert normalize_path("/users/123/posts/456") == "/users/{id}/posts/{id}"

    def test_uuid_replaced(self) -> None:
        """UUIDs in paths should be replaced."""
        path = "/users/550e8400-e29b-41d4-a716-446655440000/profile"
        assert normalize_path(path) == "/users/{uuid}/profile"

    def test_static_path_unchanged(self) -> None:
        """Static paths should be unchanged."""
        assert normalize_path("/health") == "/health"
        assert normalize_path("/api/v1/users") == "/api/v1/users"


class TestCacheMetrics:
    """Tests for cache metrics recording."""

    def test_record_cache_hit(self) -> None:
        """Cache hit should be recorded without error."""
        record_cache_hit("redis")
        record_cache_hit("memory")

    def test_record_cache_miss(self) -> None:
        """Cache miss should be recorded without error."""
        record_cache_miss("redis")

    def test_record_cache_operation(self) -> None:
        """Cache operation should be recorded without error."""
        record_cache_operation("get", "success")
        record_cache_operation("set", "error")


class TestAIMetrics:
    """Tests for AI service metrics recording."""

    def test_record_ai_request(self) -> None:
        """AI request should be recorded without error."""
        record_ai_request("itinerary", 1.5, "success")
        record_ai_request("chatbot", 0.5, "error")


class TestCircuitBreakerMetrics:
    """Tests for circuit breaker metrics recording."""

    def test_set_circuit_breaker_state(self) -> None:
        """Circuit breaker state should be recorded without error."""
        set_circuit_breaker_state("ai_breaker", "closed")
        set_circuit_breaker_state("ai_breaker", "open")
        set_circuit_breaker_state("ai_breaker", "half_open")

    def test_record_circuit_breaker_failure(self) -> None:
        """Circuit breaker failure should be recorded without error."""
        record_circuit_breaker_failure("ai_breaker")

    def test_record_circuit_breaker_success(self) -> None:
        """Circuit breaker success should be recorded without error."""
        record_circuit_breaker_success("ai_breaker")


class TestRateLimitMetrics:
    """Tests for rate limit metrics recording."""

    def test_record_rate_limit_hit(self) -> None:
        """Rate limit hit should be recorded without error."""
        record_rate_limit_hit("/api/users")
        record_rate_limit_hit("/users/123")  # Should normalize


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_format(client) -> None:
    """Test that /metrics endpoint returns Prometheus format."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    # Check for some expected metrics
    content = response.text
    assert "baliblissed" in content or "http" in content
