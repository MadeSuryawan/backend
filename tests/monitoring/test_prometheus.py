"""Tests for monitoring prometheus module."""

from app.monitoring.prometheus import (
    HIGH_CARDINALITY_LABELS,
    LATENCY_BUCKETS,
    MAX_LABEL_NAME_LENGTH,
    MAX_LABEL_VALUE_LENGTH,
    SAFE_LABELS,
    MetricsCollector,
)


class TestSanitizeEndpoint:
    """Tests for _sanitize_endpoint method."""

    def test_sanitizes_numeric_id(self) -> None:
        """Test that numeric IDs are replaced."""
        result = MetricsCollector._sanitize_endpoint("/users/12345")
        assert result == "/users/{id}"

    def test_sanitizes_uuid(self) -> None:
        """Test that UUIDs are replaced."""
        result = MetricsCollector._sanitize_endpoint("/users/550e8400-e29b-41d4-a716-446655440000")
        assert result == "/users/{uuid}"

    def test_sanitizes_nested_paths(self) -> None:
        """Test that nested paths are sanitized."""
        result = MetricsCollector._sanitize_endpoint("/users/123/posts/456")
        assert result == "/users/{id}/posts/{id}"

    def test_preserves_static_paths(self) -> None:
        """Test that static paths are preserved."""
        result = MetricsCollector._sanitize_endpoint("/health")
        assert result == "/health"

    def test_preserves_api_version(self) -> None:
        """Test that API version paths are preserved."""
        result = MetricsCollector._sanitize_endpoint("/api/v1/users/123")
        assert result == "/api/v1/users/{id}"


class TestValidateLabelName:
    """Tests for _validate_label_name method."""

    def test_rejects_high_cardinality_labels(self) -> None:
        """Test that high cardinality labels are rejected."""
        assert not MetricsCollector._validate_label_name("user_id")
        assert not MetricsCollector._validate_label_name("session_id")
        assert not MetricsCollector._validate_label_name("request_id")
        assert not MetricsCollector._validate_label_name("email")

    def test_accepts_safe_labels(self) -> None:
        """Test that safe labels are accepted."""
        assert MetricsCollector._validate_label_name("method")
        assert MetricsCollector._validate_label_name("status_code")
        assert MetricsCollector._validate_label_name("endpoint")

    def test_rejects_long_label_names(self) -> None:
        """Test that long label names are rejected."""
        long_name = "a" * 200
        assert not MetricsCollector._validate_label_name(long_name)


class TestValidateLabelValue:
    """Tests for _validate_label_value method."""

    def test_truncates_long_values(self) -> None:
        """Test that long values are truncated."""
        long_value = "a" * 2000
        result = MetricsCollector._validate_label_value(long_value)
        assert len(result) == 1024

    def test_preserves_short_values(self) -> None:
        """Test that short values are preserved."""
        short_value = "test-value"
        result = MetricsCollector._validate_label_value(short_value)
        assert result == short_value


class TestConstants:
    """Tests for module constants."""

    def test_high_cardinality_labels(self) -> None:
        """Test that high cardinality labels are defined."""
        assert "user_id" in HIGH_CARDINALITY_LABELS
        assert "session_id" in HIGH_CARDINALITY_LABELS
        assert "request_id" in HIGH_CARDINALITY_LABELS
        assert "email" in HIGH_CARDINALITY_LABELS

    def test_safe_labels(self) -> None:
        """Test that safe labels are defined."""
        assert "method" in SAFE_LABELS
        assert "status_code" in SAFE_LABELS
        assert "endpoint" in SAFE_LABELS

    def test_latency_buckets(self) -> None:
        """Test that latency buckets are defined."""
        assert len(LATENCY_BUCKETS) > 0
        assert all(isinstance(b, float) for b in LATENCY_BUCKETS)

    def test_max_label_name_length(self) -> None:
        """Test max label name length constant."""
        assert MAX_LABEL_NAME_LENGTH == 128

    def test_max_label_value_length(self) -> None:
        """Test max label value length constant."""
        assert MAX_LABEL_VALUE_LENGTH == 1024
