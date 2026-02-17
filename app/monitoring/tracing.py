"""
OpenTelemetry distributed tracing for BaliBlissed Backend.

This module provides distributed tracing using OpenTelemetry with:
- Automatic FastAPI instrumentation
- OTLP exporter for trace collection
- Configurable sampling for production cost control
- Graceful degradation when collector is unavailable
- Trace context propagation

Security:
    - No PII in span attributes
    - Excluded sensitive endpoints from tracing
"""

from __future__ import annotations

import os
from logging import getLogger
from typing import TYPE_CHECKING, Any

from app.configs import settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.trace import Span, Tracer

logger = getLogger(__name__)

# --- Constants ---
SERVICE_NAME = "baliblissed-backend"
SERVICE_VERSION = "1.0.0"

# Endpoints to exclude from tracing (reduces noise and cost)
EXCLUDED_URLS = [
    "/metrics",
    "/health",
    "/health/live",
    "/health/ready",
    "/favicon.ico",
]

# Default sampling rate (10% for production)
DEFAULT_SAMPLING_RATE = 0.1

# Sensitive attributes that should NOT be included in traces
SENSITIVE_ATTRIBUTES = frozenset({
    "http.request.header.authorization",
    "http.request.header.cookie",
    "http.request.header.x-api-key",
    "http.request.body",
    "http.response.body",
    "db.statement",  # May contain sensitive data
})


def get_sampling_rate() -> float:
    """
    Get the sampling rate from environment or settings.

    Returns
    -------
    float
        Sampling rate between 0.0 and 1.0.
    """
    # Check environment variable first
    env_rate = os.getenv("OTEL_TRACES_SAMPLER_ARG")
    if env_rate:
        try:
            return float(env_rate)
        except ValueError:
            pass

    # Use default based on environment
    if settings.ENVIRONMENT == "production":
        return DEFAULT_SAMPLING_RATE
    return 1.0  # 100% sampling in development


def get_otlp_endpoint() -> str | None:
    """
    Get the OTLP collector endpoint.

    Returns
    -------
    str | None
        OTLP endpoint URL or None if not configured.
    """
    return os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


def configure_tracing(app: FastAPI) -> bool:
    """
    Configure OpenTelemetry tracing for the FastAPI application.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.

    Returns
    -------
    bool
        True if tracing was successfully configured, False otherwise.

    Notes
    -----
    This function will not crash the application if the OTLP collector
    is unavailable. It will log a warning and continue without tracing.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
    except ImportError:
        logger.warning("OpenTelemetry packages not installed, tracing disabled")
        return False

    try:
        # Create resource attributes following semantic conventions
        resource = Resource.create({
            "service.name": SERVICE_NAME,
            "service.version": SERVICE_VERSION,
            "deployment.environment": settings.ENVIRONMENT,
            "service.namespace": "baliblissed",
            "host.name": os.uname().nodename,
        })

        # Configure sampler
        sampling_rate = get_sampling_rate()
        sampler = ParentBasedTraceIdRatio(sampling_rate)

        logger.info(
            f"Configuring tracing with sampling rate: {sampling_rate * 100:.1f}%",
        )

        # Create tracer provider
        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        # Configure exporter
        otlp_endpoint = get_otlp_endpoint()
        if otlp_endpoint:
            try:
                # Use OTLP exporter for production
                exporter = OTLPSpanExporter(
                    endpoint=otlp_endpoint,
                    insecure=settings.ENVIRONMENT != "production",
                )
                processor = BatchSpanProcessor(exporter)
                provider.add_span_processor(processor)
                logger.info(f"OTLP exporter configured for endpoint: {otlp_endpoint}")
            except Exception:
                logger.warning(
                    "Failed to configure OTLP exporter, falling back to console",
                    exc_info=True,
                )
                # Fall back to console exporter
                if settings.ENVIRONMENT == "development":
                    console_exporter = ConsoleSpanExporter()
                    processor = BatchSpanProcessor(console_exporter)
                    provider.add_span_processor(processor)
        elif settings.ENVIRONMENT == "development":
            # Use console exporter for development when no OTLP endpoint
            console_exporter = ConsoleSpanExporter()
            processor = BatchSpanProcessor(console_exporter)
            provider.add_span_processor(processor)
            logger.info("Console span exporter configured for development")
        else:
            logger.info("No OTLP endpoint configured, traces will be discarded")

        # Set the tracer provider
        trace.set_tracer_provider(provider)

        # Instrument FastAPI
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=",".join(EXCLUDED_URLS),
            tracer_provider=provider,
        )

        logger.info("OpenTelemetry tracing configured successfully")
        return True

    except Exception:
        logger.warning(
            "Failed to configure OpenTelemetry tracing, app will continue without tracing",
            exc_info=True,
        )
        return False


def shutdown_tracing() -> None:
    """
    Shutdown the tracing system gracefully.

    Should be called during application shutdown to flush any pending spans.
    """
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")
    except Exception:
        logger.warning("Error during tracing shutdown", exc_info=True)


def get_tracer(name: str | None = None) -> Tracer:
    """
    Get an OpenTelemetry tracer instance.

    Parameters
    ----------
    name : str | None
        The tracer name. Defaults to the service name.

    Returns
    -------
    Tracer
        An OpenTelemetry tracer instance.
    """
    from opentelemetry import trace

    return trace.get_tracer(name or SERVICE_NAME)


def create_span(
    name: str,
    attributes: dict[str, str | int | float | bool] | None = None,
) -> Span:
    """
    Create a new span with the given name and attributes.

    Parameters
    ----------
    name : str
        The span name.
    attributes : dict | None
        Optional span attributes.

    Returns
    -------
    Span
        The created span.

    Notes
    -----
    Sensitive attributes will be filtered out automatically.
    """
    from opentelemetry import trace

    tracer = get_tracer()

    # Filter sensitive attributes
    safe_attributes: dict[str, Any] = {}
    if attributes:
        for key, value in attributes.items():
            if key.lower() not in SENSITIVE_ATTRIBUTES:
                safe_attributes[key] = value

    return tracer.start_span(name, attributes=safe_attributes)


def add_span_attributes(attributes: dict[str, str | int | float | bool]) -> None:
    """
    Add attributes to the current span.

    Parameters
    ----------
    attributes : dict
        The attributes to add.

    Notes
    -----
    Sensitive attributes will be filtered out automatically.
    """
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            if key.lower() not in SENSITIVE_ATTRIBUTES:
                span.set_attribute(key, value)


def record_exception(exception: Exception) -> None:
    """
    Record an exception on the current span.

    Parameters
    ----------
    exception : Exception
        The exception to record.
    """
    from opentelemetry import trace

    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exception)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))


def get_current_trace_id() -> str | None:
    """
    Get the current trace ID as a hex string.

    Returns
    -------
    str | None
        The trace ID or None if no active span.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            if ctx.is_valid:
                return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None


def get_current_span_id() -> str | None:
    """
    Get the current span ID as a hex string.

    Returns
    -------
    str | None
        The span ID or None if no active span.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            if ctx.is_valid:
                return format(ctx.span_id, "016x")
    except Exception:
        pass
    return None
