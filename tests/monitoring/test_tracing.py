"""Tests for OpenTelemetry tracing functionality."""

from __future__ import annotations

import os

import pytest

from app.monitoring.tracing import (
    EXCLUDED_URLS,
    get_current_span_id,
    get_current_trace_id,
    get_otlp_endpoint,
    get_sampling_rate,
)


class TestSamplingRate:
    """Tests for sampling rate configuration."""

    def test_default_development_rate(self, monkeypatch) -> None:
        """Development should use 100% sampling by default."""
        monkeypatch.setattr("app.monitoring.tracing.settings.ENVIRONMENT", "development")
        monkeypatch.delenv("OTEL_TRACES_SAMPLER_ARG", raising=False)
        rate = get_sampling_rate()
        assert rate == 1.0

    def test_default_production_rate(self, monkeypatch) -> None:
        """Production should use 10% sampling by default."""
        monkeypatch.setattr("app.monitoring.tracing.settings.ENVIRONMENT", "production")
        monkeypatch.delenv("OTEL_TRACES_SAMPLER_ARG", raising=False)
        rate = get_sampling_rate()
        assert rate == 0.1

    def test_env_var_overrides_default(self, monkeypatch) -> None:
        """Environment variable should override default rate."""
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "0.5")
        rate = get_sampling_rate()
        assert rate == 0.5


class TestOTLPEndpoint:
    """Tests for OTLP endpoint configuration."""

    def test_no_endpoint_returns_none(self, monkeypatch) -> None:
        """No endpoint configured should return None."""
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        assert get_otlp_endpoint() is None

    def test_endpoint_from_env(self, monkeypatch) -> None:
        """Endpoint should be read from environment."""
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4317")
        assert get_otlp_endpoint() == "http://collector:4317"


class TestExcludedURLs:
    """Tests for URL exclusion."""

    def test_health_endpoints_excluded(self) -> None:
        """Health endpoints should be excluded from tracing."""
        assert "/health" in EXCLUDED_URLS
        assert "/health/live" in EXCLUDED_URLS
        assert "/health/ready" in EXCLUDED_URLS

    def test_metrics_excluded(self) -> None:
        """Metrics endpoint should be excluded from tracing."""
        assert "/metrics" in EXCLUDED_URLS


class TestTraceContext:
    """Tests for trace context retrieval."""

    def test_no_active_span_returns_none(self) -> None:
        """No active span should return None for trace/span ID."""
        assert get_current_trace_id() is None
        assert get_current_span_id() is None
