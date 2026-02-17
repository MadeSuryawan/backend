"""
Prometheus metrics collection for BaliBlissed Backend.

This module provides Prometheus metrics collection with cardinality protection,
custom metrics for cache, AI services, and circuit breaker states.

Features:
    - Standard HTTP metrics via prometheus-fastapi-instrumentator
    - Custom counters for cache hits/misses
    - AI request duration and token usage metrics
    - Circuit breaker state gauges
    - System metrics (CPU, memory, disk)
    - Cardinality protection to prevent metric explosion

Security:
    - Metrics endpoint access restriction by IP
    - No PII or high-cardinality labels (user_id, session_id, etc.)
"""

from __future__ import annotations

import ipaddress
from logging import getLogger
from typing import TYPE_CHECKING, Callable

from prometheus_client import Counter, Gauge, Histogram, Info
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info as MetricsInfo
from starlette.requests import Request
from starlette.responses import Response

from app.configs import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = getLogger(__name__)

# --- Constants ---
NAMESPACE = "baliblissed"

# Cardinality limits
MAX_SERIES_PER_METRIC = 10000
MAX_LABEL_NAME_LENGTH = 128
MAX_LABEL_VALUE_LENGTH = 1024

# High cardinality labels to NEVER use
HIGH_CARDINALITY_LABELS = frozenset({
    "user_id",
    "session_id",
    "request_id",
    "email",
    "full_path",
    "uuid",
})

# Safe labels with bounded cardinality
SAFE_LABELS = frozenset({
    "method",
    "status_code",
    "endpoint",
    "service",
    "handler",
})

# Histogram buckets for different latency profiles
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
AI_LATENCY_BUCKETS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

# Allowed IPs for /metrics endpoint (internal networks)
ALLOWED_METRICS_IPS = [
    ipaddress.ip_network("127.0.0.1/32"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]

# --- Application Info ---
app_info = Info(
    f"{NAMESPACE}_app",
    "Application information",
)

# --- Cache Metrics ---
cache_hits_total = Counter(
    f"{NAMESPACE}_cache_hits_total",
    "Total number of cache hits",
    ["cache_type"],
)

cache_misses_total = Counter(
    f"{NAMESPACE}_cache_misses_total",
    "Total number of cache misses",
    ["cache_type"],
)

cache_operations_total = Counter(
    f"{NAMESPACE}_cache_operations_total",
    "Total cache operations",
    ["operation", "status"],
)

# --- AI Service Metrics ---
ai_request_duration_seconds = Histogram(
    f"{NAMESPACE}_ai_request_duration_seconds",
    "AI request duration in seconds",
    ["request_type"],
    buckets=AI_LATENCY_BUCKETS,
)

ai_requests_total = Counter(
    f"{NAMESPACE}_ai_requests_total",
    "Total AI requests",
    ["request_type", "status"],
)

ai_tokens_used_total = Counter(
    f"{NAMESPACE}_ai_tokens_used_total",
    "Total AI tokens used",
    ["request_type", "token_type"],
)

# --- Circuit Breaker Metrics ---
circuit_breaker_state = Gauge(
    f"{NAMESPACE}_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["breaker_name"],
)

circuit_breaker_failures_total = Counter(
    f"{NAMESPACE}_circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["breaker_name"],
)

circuit_breaker_success_total = Counter(
    f"{NAMESPACE}_circuit_breaker_success_total",
    "Total circuit breaker successes",
    ["breaker_name"],
)

# --- Rate Limiter Metrics ---
rate_limit_hits_total = Counter(
    f"{NAMESPACE}_rate_limit_hits_total",
    "Total rate limit hits",
    ["endpoint"],
)

# --- System Metrics (updated periodically) ---
system_cpu_usage_percent = Gauge(
    f"{NAMESPACE}_system_cpu_usage_percent",
    "System CPU usage percentage",
)

system_memory_usage_percent = Gauge(
    f"{NAMESPACE}_system_memory_usage_percent",
    "System memory usage percentage",
)

system_memory_used_bytes = Gauge(
    f"{NAMESPACE}_system_memory_used_bytes",
    "System memory used in bytes",
)

system_disk_usage_percent = Gauge(
    f"{NAMESPACE}_system_disk_usage_percent",
    "System disk usage percentage",
)


def is_ip_allowed(client_ip: str) -> bool:
    """
    Check if client IP is allowed to access metrics endpoint.

    Parameters
    ----------
    client_ip : str
        The client's IP address.

    Returns
    -------
    bool
        True if IP is allowed, False otherwise.
    """
    try:
        ip = ipaddress.ip_address(client_ip)
        return any(ip in network for network in ALLOWED_METRICS_IPS)
    except ValueError:
        return False


def sanitize_label_value(value: str) -> str:
    """
    Sanitize label value to prevent cardinality explosion.

    Parameters
    ----------
    value : str
        The label value to sanitize.

    Returns
    -------
    str
        Sanitized label value, truncated if necessary.
    """
    if not value:
        return "unknown"
    # Truncate to max length
    return value[:MAX_LABEL_VALUE_LENGTH]


def normalize_path(path: str) -> str:
    """
    Normalize URL path to prevent high cardinality from path parameters.

    Converts paths like /users/123/profile to /users/{id}/profile.

    Parameters
    ----------
    path : str
        The URL path to normalize.

    Returns
    -------
    str
        Normalized path with IDs replaced by placeholders.
    """
    import re

    # Replace UUIDs
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{uuid}",
        path,
        flags=re.IGNORECASE,
    )
    # Replace numeric IDs
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
    return path


def record_cache_hit(cache_type: str = "redis") -> None:
    """Record a cache hit."""
    cache_hits_total.labels(cache_type=sanitize_label_value(cache_type)).inc()


def record_cache_miss(cache_type: str = "redis") -> None:
    """Record a cache miss."""
    cache_misses_total.labels(cache_type=sanitize_label_value(cache_type)).inc()


def record_cache_operation(operation: str, status: str = "success") -> None:
    """Record a cache operation."""
    cache_operations_total.labels(
        operation=sanitize_label_value(operation),
        status=sanitize_label_value(status),
    ).inc()


def record_ai_request(
    request_type: str,
    duration_seconds: float,
    status: str = "success",
) -> None:
    """
    Record an AI request with its duration.

    Parameters
    ----------
    request_type : str
        Type of AI request (itinerary, query, chatbot).
    duration_seconds : float
        Request duration in seconds.
    status : str
        Request status (success, error, timeout).
    """
    ai_request_duration_seconds.labels(
        request_type=sanitize_label_value(request_type),
    ).observe(duration_seconds)
    ai_requests_total.labels(
        request_type=sanitize_label_value(request_type),
        status=sanitize_label_value(status),
    ).inc()


def record_ai_tokens(
    request_type: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> None:
    """
    Record AI token usage.

    Parameters
    ----------
    request_type : str
        Type of AI request.
    input_tokens : int
        Number of input tokens used.
    output_tokens : int
        Number of output tokens generated.
    """
    if input_tokens > 0:
        ai_tokens_used_total.labels(
            request_type=sanitize_label_value(request_type),
            token_type="input",
        ).inc(input_tokens)
    if output_tokens > 0:
        ai_tokens_used_total.labels(
            request_type=sanitize_label_value(request_type),
            token_type="output",
        ).inc(output_tokens)


def set_circuit_breaker_state(breaker_name: str, state: str) -> None:
    """
    Set circuit breaker state metric.

    Parameters
    ----------
    breaker_name : str
        Name of the circuit breaker.
    state : str
        State of the circuit breaker (closed, open, half_open).
    """
    state_map = {"closed": 0, "open": 1, "half_open": 2}
    state_value = state_map.get(state.lower(), 0)
    circuit_breaker_state.labels(
        breaker_name=sanitize_label_value(breaker_name),
    ).set(state_value)


def record_circuit_breaker_failure(breaker_name: str) -> None:
    """Record a circuit breaker failure."""
    circuit_breaker_failures_total.labels(
        breaker_name=sanitize_label_value(breaker_name),
    ).inc()


def record_circuit_breaker_success(breaker_name: str) -> None:
    """Record a circuit breaker success."""
    circuit_breaker_success_total.labels(
        breaker_name=sanitize_label_value(breaker_name),
    ).inc()


def record_rate_limit_hit(endpoint: str) -> None:
    """Record a rate limit hit."""
    rate_limit_hits_total.labels(
        endpoint=sanitize_label_value(normalize_path(endpoint)),
    ).inc()


async def update_system_metrics() -> None:
    """
    Update system metrics (CPU, memory, disk).

    This should be called periodically or on each metrics scrape.
    """
    from psutil import cpu_percent, disk_usage, virtual_memory

    try:
        # CPU usage (non-blocking sample)
        cpu = cpu_percent(interval=None)
        system_cpu_usage_percent.set(cpu)

        # Memory usage
        mem = virtual_memory()
        system_memory_usage_percent.set(mem.percent)
        system_memory_used_bytes.set(mem.used)

        # Disk usage (root partition)
        disk = disk_usage("/")
        system_disk_usage_percent.set(disk.percent)
    except Exception:
        logger.exception("Failed to update system metrics")


def create_instrumentator() -> Instrumentator:
    """
    Create and configure the Prometheus FastAPI Instrumentator.

    Returns
    -------
    Instrumentator
        Configured instrumentator instance.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health", "/health/live", "/health/ready"],
        env_var_name="ENABLE_METRICS",
        inprogress_name=f"{NAMESPACE}_http_requests_inprogress",
        inprogress_labels=True,
    )

    # Add default metrics
    instrumentator.add(
        metrics.default(
            metric_namespace=NAMESPACE,
            metric_subsystem="http",
            latency_highr_buckets=LATENCY_BUCKETS,
        ),
    )

    # Add request size metric
    instrumentator.add(
        metrics.request_size(
            metric_namespace=NAMESPACE,
            metric_subsystem="http",
        ),
    )

    # Add response size metric
    instrumentator.add(
        metrics.response_size(
            metric_namespace=NAMESPACE,
            metric_subsystem="http",
        ),
    )

    return instrumentator


def setup_metrics(app: FastAPI) -> Instrumentator:
    """
    Set up Prometheus metrics for the FastAPI application.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.

    Returns
    -------
    Instrumentator
        The configured instrumentator.

    Notes
    -----
    This function should be called during application startup in the lifespan
    context manager.
    """
    # Set application info
    app_info.info({
        "version": app.version or "1.0.0",
        "environment": settings.ENVIRONMENT,
        "service_name": "baliblissed-backend",
    })

    # Create and instrument the app
    instrumentator = create_instrumentator()

    # Register custom metrics callback
    instrumentator.add(metrics_callback)

    instrumentator.instrument(app)

    logger.info("Prometheus metrics initialized")

    return instrumentator


def expose_metrics(app: FastAPI, instrumentator: Instrumentator) -> None:
    """
    Expose the /metrics endpoint for Prometheus scraping.

    The endpoint is protected by IP allowlist - only requests from
    internal networks (127.0.0.1, 10.x.x.x, 172.16-31.x.x, 192.168.x.x)
    are allowed to access metrics.

    Parameters
    ----------
    app : FastAPI
        The FastAPI application instance.
    instrumentator : Instrumentator
        The instrumentator instance from setup_metrics.
    """
    from fastapi import HTTPException
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    from starlette.responses import Response as StarletteResponse

    @app.get("/metrics", include_in_schema=False, tags=["Monitoring"])
    async def metrics_endpoint(request: Request) -> StarletteResponse:
        """
        Prometheus metrics endpoint with IP protection.

        Only allows access from internal/trusted IP addresses.
        """
        # Get client IP from request
        client_ip = request.client.host if request.client else "unknown"

        # Check if IP is allowed
        if not is_ip_allowed(client_ip):
            logger.warning(f"Metrics access denied for IP: {client_ip}")
            raise HTTPException(
                status_code=403,
                detail="Access to metrics endpoint is restricted",
            )

        # Update system metrics before generating output
        await update_system_metrics()

        # Generate metrics output
        metrics_output = generate_latest()
        return StarletteResponse(
            content=metrics_output,
            media_type=CONTENT_TYPE_LATEST,
        )

    logger.info("Prometheus /metrics endpoint exposed with IP protection")


def metrics_callback(info: MetricsInfo) -> None:
    """
    Callback for updating custom metrics after each request.

    This is registered with the instrumentator to collect system metrics
    periodically during normal request processing.

    Parameters
    ----------
    info : MetricsInfo
        Request/response information from the instrumentator.
    """
    # Note: We can't use async here as instrumentator callbacks are sync.
    # System metrics are updated in the /metrics endpoint handler instead.
    # This callback can be used for other sync metric updates if needed.
    pass
