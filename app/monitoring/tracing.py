"""
Distributed tracing with OpenTelemetry.

This module provides distributed tracing capabilities using OpenTelemetry with:
- FastAPI auto-instrumentation
- Configurable sampling rates
- OTLP export support
- Graceful degradation when collector is unavailable
- Resource attributes following semantic conventions

Configuration
-------------
Environment variables:
- OTEL_SERVICE_NAME: Service name for traces (default: baliblissed-backend)
- OTEL_EXPORTER_OTLP_ENDPOINT: OTLP collector endpoint
- OTEL_TRACES_SAMPLER_ARG: Sampling ratio (default: 1.0 for dev, 0.1 for prod)
- OTEL_PYTHON_FASTAPI_EXCLUDED_URLS: URLs to exclude from tracing

Examples
--------
>>> from app.monitoring import tracer, setup_tracing
>>> setup_tracing(app)
>>> with tracer.start_as_current_span("my_operation") as span:
...     span.set_attribute("key", "value")
"""

from logging import getLogger
from os import environ
from platform import node

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.trace.sampling import (
    ALWAYS_ON,
    ParentBasedTraceIdRatio,
    Sampler,
)
from opentelemetry.trace import (
    get_current_span,
    get_tracer,
    get_tracer_provider,
    set_tracer_provider,
)

from app.configs.settings import settings

# Default excluded URLs (health checks and metrics)
DEFAULT_EXCLUDED_URLS = "/metrics,/health,/health/live,/health/ready,/favicon.ico"


def get_sampler() -> Sampler:
    """
    Get the appropriate sampler based on environment.

    Returns:
        Configured Sampler instance.

    Examples:
    --------
    >>> sampler = get_sampler()
    """
    if settings.ENVIRONMENT == "development":
        # 100% sampling in development
        return ALWAYS_ON

    ratio = settings.OTEL_TRACES_SAMPLER_ARG

    return ParentBasedTraceIdRatio(ratio)


def create_resource() -> Resource:
    """
    Create OpenTelemetry Resource with semantic conventions.

    Returns:
        Resource with service attributes.

    Examples:
    --------
    >>> resource = create_resource()
    """
    service_name = environ.get("OTEL_SERVICE_NAME", "baliblissed-backend")
    service_version = environ.get("OTEL_SERVICE_VERSION", "1.0.0")

    return Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": settings.ENVIRONMENT,
            "host.name": node(),
            "service.namespace": "baliblissed",
            "service.instance.id": environ.get("HOSTNAME", "unknown"),
        },
    )


def setup_tracing(app: FastAPI) -> TracerProvider | None:
    """
    Set up OpenTelemetry tracing for the FastAPI application.

    This function configures distributed tracing with OTLP export and
    FastAPI auto-instrumentation. The application continues to function
    even if the OTLP collector is unavailable.

    Args:
        app: The FastAPI application instance.

    Returns:
        Configured TracerProvider or None if setup failed.

    Examples:
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> provider = setup_tracing(app)
    """
    try:
        # Create resource
        resource = create_resource()

        # Create tracer provider with sampler
        provider = TracerProvider(
            resource=resource,
            sampler=get_sampler(),
        )

        # Set as global tracer provider
        set_tracer_provider(provider)

        # Configure exporters
        _configure_exporters(provider)

        # Instrument FastAPI
        _instrument_fastapi(app)

        return provider

    except (RuntimeError, SystemError) as e:
        # Log warning but don't crash the app
        logger = getLogger(__name__)
        logger.warning(f"Failed to setup tracing: {e}. Continuing without tracing.")
        return None


def _configure_exporters(provider: TracerProvider) -> None:
    """
    Configure span exporters for the tracer provider.

    Args:
        provider: The TracerProvider to configure.
    """
    # Check for OTLP endpoint
    otlp_endpoint = environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if otlp_endpoint:
        try:
            # Create OTLP exporter
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                insecure=otlp_endpoint.startswith("http://"),
            )
            provider.add_span_processor(
                BatchSpanProcessor(
                    otlp_exporter,
                    max_queue_size=2048,
                    max_export_batch_size=512,
                    schedule_delay_millis=5000,
                ),
            )
        except (RuntimeError, SystemError) as e:
            logger = getLogger(__name__)
            logger.warning(f"Failed to configure OTLP exporter: {e}")

    # Add console exporter only if explicitly enabled via OTEL_CONSOLE_EXPORT_ENABLED
    # This prevents noisy JSON span logs in development console output
    if settings.OTEL_CONSOLE_EXPORT_ENABLED:
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(
            BatchSpanProcessor(
                console_exporter,
                max_queue_size=512,
                max_export_batch_size=128,
            ),
        )


def _instrument_fastapi(app: FastAPI) -> None:
    """
    Instrument FastAPI with OpenTelemetry.

    Args:
        app: The FastAPI application to instrument.
    """
    try:
        # Get excluded URLs from environment or use defaults
        excluded_urls = environ.get(
            "OTEL_PYTHON_FASTAPI_EXCLUDED_URLS",
            DEFAULT_EXCLUDED_URLS,
        )

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=excluded_urls,
            tracer_provider=get_tracer_provider(),
        )

    except (RuntimeError, SystemError) as e:
        logger = getLogger(__name__)
        logger.warning(f"Failed to instrument FastAPI: {e}")


# Global tracer instance
tracer = get_tracer("baliblissed-backend")


def add_span_attributes(**kwargs: str | int | float | bool) -> None:
    """
    Add attributes to the current span.

    Args:
        **kwargs: Key-value pairs to add as span attributes.

    Examples:
    --------
    >>> add_span_attributes(user_id="123", action="login")
    """
    current_span = get_current_span()
    if current_span:
        for key, value in kwargs.items():
            current_span.set_attribute(key, value)


def record_exception(exception: Exception) -> None:
    """
    Record an exception in the current span.

    Args:
        exception: The exception to record.

    Examples:
    --------
    >>> try:
    ...     risky_operation()
    ... except Exception as e:
    ...     record_exception(e)
    """
    current_span = get_current_span()
    if current_span:
        current_span.record_exception(exception)
