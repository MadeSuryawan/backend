"""
Metrics and monitoring service for tracking API performance.

This module provides thread-safe metrics collection and monitoring capabilities
for tracking API performance, request counts, response times, and error rates.

Features:
    - Thread-safe counters using threading.Lock
    - Memory-efficient circular buffer using deque for response times
    - Async context manager support for request timing
    - System metrics collection (CPU, memory, disk)
"""

from asyncio import to_thread
from collections import defaultdict, deque
from dataclasses import dataclass, field
from logging import getLogger
from threading import Lock
from time import perf_counter
from types import TracebackType
from typing import Any, Self

from psutil import cpu_percent as get_cpu_percent
from psutil import disk_usage, virtual_memory

from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


# Constants
_BYTES_PER_MB: int = 1024 * 1024
_MAX_RESPONSE_TIMES: int = 1000
_CPU_SAMPLE_INTERVAL: float = 0.1  # Reduced from 1s for faster response


@dataclass(slots=True)
class ResponseTimeStats:
    """
    Statistics for response times with O(1) operations.

    Uses deque for automatic circular buffer behavior (memory-efficient).
    Pre-calculates sum for O(1) average computation.
    """

    times: deque[float] = field(default_factory=lambda: deque(maxlen=_MAX_RESPONSE_TIMES))
    _sum: float = field(default=0.0, repr=False)

    def add(self, duration: float) -> None:
        """Add a response time, maintaining running sum for O(1) average."""
        if len(self.times) == self.times.maxlen:
            # Remove oldest value from sum before it's evicted
            self._sum -= self.times[0]
        self.times.append(duration)
        self._sum += duration

    @property
    def average(self) -> float:
        """Get average response time in O(1)."""
        return self._sum / len(self.times) if self.times else 0.0

    @property
    def count(self) -> int:
        """Get number of recorded times."""
        return len(self.times)

    def clear(self) -> None:
        """Clear all recorded times."""
        self.times.clear()
        self._sum = 0.0


class MetricsManager:
    """
    Thread-safe metrics collector for API performance tracking.

    All counter operations are protected by locks for thread safety.
    Uses memory-efficient data structures (deque, slots).
    """

    __slots__ = (
        "_lock",
        "_request_counts",
        "_error_counts",
        "_response_times",
        "_ai_request_counts",
        "_cache_hits",
        "_cache_misses",
        "_circuit_breaker_opens",
        "_rate_limit_hits",
    )

    def __init__(self) -> None:
        """Initialize thread-safe metrics collector."""
        self._lock = Lock()
        self._request_counts: dict[str, int] = defaultdict(int)
        self._error_counts: dict[str, int] = defaultdict(int)
        self._response_times: dict[str, ResponseTimeStats] = defaultdict(ResponseTimeStats)
        self._ai_request_counts: dict[str, int] = defaultdict(int)
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._circuit_breaker_opens: int = 0
        self._rate_limit_hits: int = 0

    def record_request(self, endpoint: str) -> None:
        """
        Record an API request (thread-safe).

        Args:
            endpoint: API endpoint path.
        """
        with self._lock:
            self._request_counts[endpoint] += 1

    def record_error(self, endpoint: str) -> None:
        """
        Record an API error (thread-safe).

        Args:
            endpoint: API endpoint path.
        """
        with self._lock:
            self._error_counts[endpoint] += 1

    def record_response_time(self, endpoint: str, duration: float) -> None:
        """
        Record response time for an endpoint (thread-safe).

        Uses deque with maxlen for automatic memory management.

        Args:
            endpoint: API endpoint path.
            duration: Response time in seconds.
        """
        with self._lock:
            self._response_times[endpoint].add(duration)

    def record_ai_request(self, request_type: str) -> None:
        """
        Record an AI API request (thread-safe).

        Args:
            request_type: Type of AI request (itinerary, query, contact).
        """
        with self._lock:
            self._ai_request_counts[request_type] += 1

    def record_cache_hit(self) -> None:
        """Record a cache hit (thread-safe)."""
        with self._lock:
            self._cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss (thread-safe)."""
        with self._lock:
            self._cache_misses += 1

    def record_circuit_breaker_open(self) -> None:
        """Record a circuit breaker opening (thread-safe)."""
        with self._lock:
            self._circuit_breaker_opens += 1

    def record_rate_limit_hit(self) -> None:
        """Record a rate limit hit (thread-safe)."""
        with self._lock:
            self._rate_limit_hits += 1

    def get_metrics(self) -> dict[str, Any]:
        """
        Get current metrics summary (thread-safe snapshot).

        Returns:
            Dictionary containing all metrics with computed statistics.
        """
        with self._lock:
            # Compute averages using O(1) pre-calculated sums
            avg_response_times = {
                endpoint: stats.average
                for endpoint, stats in self._response_times.items()
                if stats.count > 0
            }

            # Calculate cache hit rate
            total_cache = self._cache_hits + self._cache_misses
            cache_hit_rate = (self._cache_hits / total_cache * 100) if total_cache > 0 else 0.0

            return {
                "request_counts": dict(self._request_counts),
                "error_counts": dict(self._error_counts),
                "avg_response_times": avg_response_times,
                "ai_request_counts": dict(self._ai_request_counts),
                "cache_stats": {
                    "hits": self._cache_hits,
                    "misses": self._cache_misses,
                    "hit_rate": f"{cache_hit_rate:.2f}%",
                },
                "circuit_breaker_opens": self._circuit_breaker_opens,
                "rate_limit_hits": self._rate_limit_hits,
            }

    def reset_metrics(self) -> None:
        """Reset all metrics (thread-safe)."""
        with self._lock:
            self._request_counts.clear()
            self._error_counts.clear()
            self._response_times.clear()
            self._ai_request_counts.clear()
            self._cache_hits = 0
            self._cache_misses = 0
            self._circuit_breaker_opens = 0
            self._rate_limit_hits = 0
        logger.info("Metrics reset")


# Global metrics collector instance (singleton pattern)
metrics_manager = MetricsManager()


class RequestTimer:
    """
    Context manager for timing requests with automatic metrics recording.

    Supports both sync and async usage patterns.
    Uses perf_counter for high-precision timing.
    """

    __slots__ = ("_endpoint", "_start_time", "_metrics")

    def __init__(
        self,
        endpoint: str,
        metrics: MetricsManager | None = None,
    ) -> None:
        """
        Initialize request timer.

        Args:
            endpoint: API endpoint path.
            metrics: Optional metrics manager (defaults to global instance).
        """
        self._endpoint = endpoint
        self._start_time: float = 0.0
        self._metrics = metrics or metrics_manager

    def __enter__(self) -> Self:
        """Start timer and record request."""
        self._start_time = perf_counter()
        self._metrics.record_request(self._endpoint)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: TracebackType | None,
    ) -> None:
        """Stop timer and record metrics."""
        duration = perf_counter() - self._start_time
        self._metrics.record_response_time(self._endpoint, duration)

        if exc_type is not None:
            self._metrics.record_error(self._endpoint)

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        self.__exit__(exc_type, exc_val, exc_tb)

    @property
    def elapsed(self) -> float:
        """Get elapsed time since timer started."""
        return perf_counter() - self._start_time if self._start_time else 0.0


@dataclass(slots=True, frozen=True)
class SystemMetrics:
    """Immutable system metrics snapshot."""

    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for API response."""
        return {
            "cpu_percent": self.cpu_percent,
            "memory": {
                "percent": self.memory_percent,
                "used_mb": self.memory_used_mb,
                "total_mb": self.memory_total_mb,
            },
            "disk_percent": self.disk_percent,
        }


async def get_system_metrics() -> dict[str, Any]:
    """
    Get system-level metrics asynchronously.

    Runs blocking psutil calls in a thread pool to avoid blocking the event loop.

    Returns:
        Dictionary containing system metrics or error information.
    """

    def _collect_metrics() -> SystemMetrics:
        """Collect system metrics (blocking operation)."""
        memory = virtual_memory()
        disk = disk_usage("/")

        # percpu=False (default) returns float, not list

        return SystemMetrics(
            cpu_percent=get_cpu_percent(interval=_CPU_SAMPLE_INTERVAL),
            memory_percent=memory.percent,
            memory_used_mb=round(memory.used / _BYTES_PER_MB, 2),
            memory_total_mb=round(memory.total / _BYTES_PER_MB, 2),
            disk_percent=disk.percent,
        )

    try:
        # Run blocking psutil calls in thread pool
        system_metrics = await to_thread(_collect_metrics)
        return system_metrics.to_dict()

    except OSError as e:
        logger.exception("Failed to get system metrics: OS error")
        return {"error": f"Failed to collect system metrics: {e}"}
    except Exception:
        logger.exception("Failed to get system metrics: unexpected error")
        return {"error": "Failed to collect system metrics"}
