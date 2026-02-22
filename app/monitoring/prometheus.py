"""
Prometheus metrics collection with cardinality protection.

This module provides Prometheus metrics collection for the BaliBlissed backend
with built-in cardinality protection and custom metrics for:
- HTTP request metrics (handled by prometheus-fastapi-instrumentator)
- Cache hit/miss rates
- AI request duration and token usage
- Circuit breaker states
- System metrics (CPU, memory, disk)

Security
--------
- High cardinality labels are filtered to prevent memory exhaustion
- Metrics endpoint access should be restricted to internal IPs
- User IDs, session IDs, and emails are NEVER used as labels

Examples
--------
>>> from app.monitoring import metrics
>>> metrics.record_cache_hit()
>>> metrics.record_ai_request(duration=1.5, tokens=150)
"""

from re import IGNORECASE, sub

from fastapi import FastAPI
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_fastapi_instrumentator import Instrumentator

from app.configs import settings

# Cardinality protection - NEVER use these as labels
HIGH_CARDINALITY_LABELS: frozenset[str] = frozenset(
    {
        "user_id",  # Unbounded unique values
        "session_id",  # Unbounded unique values
        "request_id",  # Unique per request
        "email",  # PII + high cardinality
        "full_path",  # Can include IDs like /users/12345
        "ip_address",  # High cardinality
    },
)

# Safe labels with bounded cardinality
SAFE_LABELS: frozenset[str] = frozenset(
    {
        "method",  # GET, POST, PUT, DELETE (4 values)
        "status_code",  # HTTP status codes (~50 values)
        "endpoint",  # Route pattern /users/{id} (bounded)
        "service",  # Known service names
    },
)

# Cardinality limits
MAX_SERIES_PER_METRIC: int = 10000
MAX_LABEL_NAME_LENGTH: int = 128
MAX_LABEL_VALUE_LENGTH: int = 1024

# Latency buckets based on expected latency profile
LATENCY_BUCKETS: tuple[float, ...] = (
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

# AI latency buckets for longer processing times
AI_LATENCY_BUCKETS: tuple[float, ...] = (
    0.1,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)


class MetricsCollector:
    """
    Metrics collector with cardinality protection.

    This class provides custom Prometheus metrics for the BaliBlissed backend
    with safeguards against high cardinality labels.

    Attributes
    ----------
    cache_hits_total : Counter
        Total number of cache hits
    cache_misses_total : Counter
        Total number of cache misses
    ai_requests_total : Counter
        Total number of AI API requests
    ai_request_duration_seconds : Histogram
        AI request duration in seconds
    ai_tokens_used_total : Counter
        Total tokens used in AI requests
    circuit_breaker_state : Gauge
        Current state of circuit breakers (0=closed, 1=open, 2=half-open)
    rate_limit_hits_total : Counter
        Total number of rate limit hits
    system_cpu_percent : Gauge
        Current CPU usage percentage
    system_memory_percent : Gauge
        Current memory usage percentage
    system_disk_percent : Gauge
        Current disk usage percentage
    """

    def __init__(self) -> None:
        """Initialize the metrics collector with all custom metrics."""
        # Cache metrics
        self.cache_hits_total = Counter(
            "baliblissed_cache_hits_total",
            "Total number of cache hits",
        )
        self.cache_misses_total = Counter(
            "baliblissed_cache_misses_total",
            "Total number of cache misses",
        )

        # AI metrics
        self.ai_requests_total = Counter(
            "baliblissed_ai_requests_total",
            "Total number of AI API requests",
            ["request_type"],  # itinerary, query, contact
        )
        self.ai_request_duration_seconds = Histogram(
            "baliblissed_ai_request_duration_seconds",
            "AI request duration in seconds",
            ["request_type"],
            buckets=AI_LATENCY_BUCKETS,
        )
        self.ai_tokens_used_total = Counter(
            "baliblissed_ai_tokens_used_total",
            "Total tokens used in AI requests",
            ["request_type"],
        )

        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            "baliblissed_circuit_breaker_state",
            "Current state of circuit breakers (0=closed, 1=open, 2=half-open)",
            ["breaker_name"],  # ai_circuit_breaker, email_circuit_breaker
        )
        self.circuit_breaker_opens_total = Counter(
            "baliblissed_circuit_breaker_opens_total",
            "Total number of circuit breaker opens",
            ["breaker_name"],
        )

        # Rate limiting metrics
        self.rate_limit_hits_total = Counter(
            "baliblissed_rate_limit_hits_total",
            "Total number of rate limit hits",
            ["endpoint"],
        )

        # System metrics
        self.system_cpu_percent = Gauge(
            "baliblissed_system_cpu_percent",
            "Current CPU usage percentage",
        )
        self.system_memory_percent = Gauge(
            "baliblissed_system_memory_percent",
            "Current memory usage percentage",
        )
        self.system_disk_percent = Gauge(
            "baliblissed_system_disk_percent",
            "Current disk usage percentage",
        )
        self.system_memory_used_bytes = Gauge(
            "baliblissed_system_memory_used_bytes",
            "Current memory usage in bytes",
        )
        self.system_memory_total_bytes = Gauge(
            "baliblissed_system_memory_total_bytes",
            "Total system memory in bytes",
        )

    @staticmethod
    def _validate_label_name(name: str) -> bool:
        """
        Validate that a label name is safe to use.

        Args:
            name: The label name to validate.

        Returns:
            True if the label name is valid, False otherwise.
        """
        if name in HIGH_CARDINALITY_LABELS:
            return False
        return len(name) <= MAX_LABEL_NAME_LENGTH

    @staticmethod
    def _validate_label_value(value: str) -> str:
        """
        Validate and truncate label values.

        Args:
            value: The label value to validate.

        Returns:
            Truncated value if needed.
        """
        if len(value) > MAX_LABEL_VALUE_LENGTH:
            return value[:MAX_LABEL_VALUE_LENGTH]
        return value

    def record_cache_hit(self) -> None:
        """
        Record a cache hit.

        Examples
        --------
        >>> metrics.record_cache_hit()
        """
        self.cache_hits_total.inc()

    def record_cache_miss(self) -> None:
        """
        Record a cache miss.

        Examples
        --------
        >>> metrics.record_cache_miss()
        """
        self.cache_misses_total.inc()

    def record_ai_request(
        self,
        request_type: str,
        duration: float | None = None,
        tokens: int | None = None,
    ) -> None:
        """
        Record an AI request with optional duration and token count.

        Args:
            request_type: Type of AI request (itinerary, query, contact).
            duration: Request duration in seconds (optional).
            tokens: Number of tokens used (optional).

        Examples:
        --------
        >>> metrics.record_ai_request("itinerary", duration=1.5, tokens=150)
        """
        # Validate and sanitize request_type
        request_type = self._validate_label_value(request_type)

        self.ai_requests_total.labels(request_type=request_type).inc()

        if duration is not None:
            self.ai_request_duration_seconds.labels(
                request_type=request_type,
            ).observe(duration)

        if tokens is not None:
            self.ai_tokens_used_total.labels(request_type=request_type).inc(tokens)

    def set_circuit_breaker_state(self, breaker_name: str, state: int) -> None:
        """
        Set the current state of a circuit breaker.

        Args:
            breaker_name: Name of the circuit breaker.
            state: State value (0=closed, 1=open, 2=half-open).

        Examples:
        --------
        >>> metrics.set_circuit_breaker_state("ai_circuit_breaker", 1)
        """
        breaker_name = self._validate_label_value(breaker_name)
        self.circuit_breaker_state.labels(breaker_name=breaker_name).set(state)

    def record_rate_limit_hit(self, endpoint: str) -> None:
        """
        Record a rate limit hit.

        Args:
            endpoint: The endpoint that was rate limited.

        Examples:
        --------
        >>> metrics.record_rate_limit_hit("/api/users")
        """
        # Sanitize endpoint to pattern (remove IDs)
        endpoint = self._sanitize_endpoint(endpoint)
        endpoint = self._validate_label_value(endpoint)
        self.rate_limit_hits_total.labels(endpoint=endpoint).inc()

    def update_system_metrics(
        self,
        cpu_percent: float,
        memory_percent: float,
        disk_percent: float,
        memory_used_bytes: int | None = None,
        memory_total_bytes: int | None = None,
    ) -> None:
        """
        Update system metrics gauges.

        Args:
            cpu_percent: CPU usage percentage.
            memory_percent: Memory usage percentage.
            disk_percent: Disk usage percentage.
            memory_used_bytes: Memory used in bytes (optional).
            memory_total_bytes: Total memory in bytes (optional).

        Examples:
        --------
        >>> metrics.update_system_metrics(45.2, 62.1, 30.5)
        """
        self.system_cpu_percent.set(cpu_percent)
        self.system_memory_percent.set(memory_percent)
        self.system_disk_percent.set(disk_percent)

        if memory_used_bytes is not None:
            self.system_memory_used_bytes.set(memory_used_bytes)
        if memory_total_bytes is not None:
            self.system_memory_total_bytes.set(memory_total_bytes)

    @staticmethod
    def _sanitize_endpoint(endpoint: str) -> str:
        """
        Sanitize endpoint path by replacing IDs with placeholders.

        Args:
            endpoint: Raw endpoint path.

        Returns:
            Sanitized endpoint pattern.

        Examples:
        --------
        >>> MetricsCollector._sanitize_endpoint("/users/12345/posts")
        '/users/{id}/posts'
        """

        # Replace UUIDs
        endpoint = sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{uuid}",
            endpoint,
            flags=IGNORECASE,
        )
        # Replace numeric IDs
        endpoint = sub(r"/\d+", "/{id}", endpoint)

        return endpoint


# Global metrics collector instance
metrics = MetricsCollector()


def setup_prometheus(app: FastAPI) -> Instrumentator:
    """
    Set up Prometheus instrumentation for the FastAPI app.

    This function configures the prometheus-fastapi-instrumentator with
    appropriate metrics and cardinality protection.

    Args:
        app: The FastAPI application instance.

    Returns:
        Configured Instrumentator instance.

    Examples:
    --------
    >>> from fastapi import FastAPI
    >>> app = FastAPI()
    >>> instrumentator = setup_prometheus(app)
    """
    # Create instrumentator
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,  # Use settings instead of direct env var
        should_instrument_requests_inprogress=True,
        excluded_handlers=[".*admin.*", "/metrics", "/health.*"],
        inprogress_name="baliblissed_http_requests_inprogress",
        inprogress_labels=True,
    )

    # Instrument the app ONLY if ENABLE_METRICS is true in settings
    if settings.ENABLE_METRICS:
        instrumentator.instrument(app)

        # Expose metrics endpoint
        instrumentator.expose(
            app,
            endpoint="/metrics",
            include_in_schema=False,
            tags=["Monitoring"],
        )

    return instrumentator


def generate_metrics_response() -> tuple[bytes, str]:
    """
    Generate Prometheus metrics response.

    Returns:
        Tuple of (metrics_bytes, content_type).

    Examples:
    --------
    >>> data, content_type = generate_metrics_response()
    """
    return generate_latest(), CONTENT_TYPE_LATEST
