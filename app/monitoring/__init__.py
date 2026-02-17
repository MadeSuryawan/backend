"""
Monitoring and observability module for BaliBlissed Backend.

This module provides a comprehensive observability stack including:
- Prometheus metrics collection
- Structured logging with PII sanitization
- OpenTelemetry distributed tracing
- Kubernetes-compatible health checks

Usage
-----
>>> from app.monitoring import setup_monitoring
>>> setup_monitoring(app)

Or import individual components:
>>> from app.monitoring.prometheus import record_cache_hit, record_ai_request
>>> from app.monitoring.logging import get_logger, set_request_id
>>> from app.monitoring.tracing import get_tracer, create_span
>>> from app.monitoring.health import setup_health_routes
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from prometheus_fastapi_instrumentator import Instrumentator

logger = getLogger(__name__)

# --- Public API ---
__all__ = [
    # Main setup function
    "setup_monitoring",
    "shutdown_monitoring",
    # Prometheus metrics
    "record_cache_hit",
    "record_cache_miss",
    "record_cache_operation",
    "record_ai_request",
    "record_ai_tokens",
    "record_rate_limit_hit",
    "set_circuit_breaker_state",
    "record_circuit_breaker_failure",
    "record_circuit_breaker_success",
    "update_system_metrics",
    # Logging
    "configure_structlog",
    "get_logger",
    "set_request_id",
    "set_user_id",
    "set_client_ip",
    "get_request_id",
    "sanitize_headers",
    "sanitize_log_message",
    # Tracing
    "configure_tracing",
    "shutdown_tracing",
    "get_tracer",
    "create_span",
    "add_span_attributes",
    "record_exception",
    "get_current_trace_id",
    "get_current_span_id",
    # Health
    "setup_health_routes",
    "perform_liveness_check",
    "perform_readiness_check",
    "HealthStatus",
    "HealthResponse",
]

# Re-export from submodules
from app.monitoring.health import (
    HealthResponse,
    HealthStatus,
    perform_liveness_check,
    perform_readiness_check,
    setup_health_routes,
)
from app.monitoring.logging import (
    configure_structlog,
    get_logger,
    get_request_id,
    sanitize_headers,
    sanitize_log_message,
    set_client_ip,
    set_request_id,
    set_user_id,
)
from app.monitoring.prometheus import (
    expose_metrics,
    record_ai_request,
    record_ai_tokens,
    record_cache_hit,
    record_cache_miss,
    record_cache_operation,
    record_circuit_breaker_failure,
    record_circuit_breaker_success,
    record_rate_limit_hit,
    set_circuit_breaker_state,
    setup_metrics,
    update_system_metrics,
)
from app.monitoring.tracing import (
    add_span_attributes,
    configure_tracing,
    create_span,
    get_current_span_id,
    get_current_trace_id,
    get_tracer,
    record_exception,
    shutdown_tracing,
)

# Module-level state
_instrumentator: Instrumentator | None = None


def setup_monitoring(app: FastAPI, *, enable_tracing: bool = True) -> None:
    """
    Set up all monitoring components for the FastAPI application.

    This function initializes:
    1. Structlog for structured logging
    2. Prometheus metrics with FastAPI instrumentator
    3. OpenTelemetry tracing (optional)
    4. Kubernetes health check endpoints

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    enable_tracing : bool
        Whether to enable OpenTelemetry tracing. Default True.

    Examples
    --------
    >>> from fastapi import FastAPI
    >>> from app.monitoring import setup_monitoring
    >>> app = FastAPI()
    >>> setup_monitoring(app)
    """
    global _instrumentator

    logger.info("Setting up monitoring stack...")

    # 1. Configure structured logging
    configure_structlog()
    logger.info("Structlog configured")

    # 2. Set up Prometheus metrics
    _instrumentator = setup_metrics(app)
    expose_metrics(app, _instrumentator)
    logger.info("Prometheus metrics configured")

    # 3. Set up health check routes
    setup_health_routes(app)
    logger.info("Health check routes configured")

    # 4. Set up OpenTelemetry tracing (optional)
    if enable_tracing:
        tracing_enabled = configure_tracing(app)
        if tracing_enabled:
            logger.info("OpenTelemetry tracing configured")
        else:
            logger.info("OpenTelemetry tracing disabled or failed to initialize")

    logger.info("Monitoring stack setup complete")


def shutdown_monitoring() -> None:
    """
    Shutdown all monitoring components gracefully.

    Should be called during application shutdown to ensure
    all pending metrics and traces are flushed.
    """
    logger.info("Shutting down monitoring stack...")

    # Shutdown tracing
    shutdown_tracing()

    logger.info("Monitoring stack shutdown complete")
