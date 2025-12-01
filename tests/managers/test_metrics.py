# tests/managers/test_metrics.py
"""Comprehensive tests for app/managers/metrics.py module."""

from asyncio import sleep as async_sleep
from collections import deque
from threading import Thread
from time import sleep
from unittest.mock import patch

import pytest

from app.decorators import timed
from app.managers.metrics import (
    _MAX_RESPONSE_TIMES,
    MetricsManager,
    RequestTimer,
    ResponseTimeStats,
    SystemMetrics,
    get_system_metrics,
    metrics_manager,
)


class TestResponseTimeStats:
    """Tests for ResponseTimeStats dataclass."""

    def test_init_creates_empty_deque(self) -> None:
        """Test initialization creates empty deque with correct maxlen."""
        stats = ResponseTimeStats()
        assert len(stats.times) == 0
        assert stats.times.maxlen == _MAX_RESPONSE_TIMES
        assert stats._sum == 0.0

    def test_add_single_value(self) -> None:
        """Test adding a single value updates times and sum."""
        stats = ResponseTimeStats()
        stats.add(1.5)
        assert len(stats.times) == 1
        assert stats._sum == 1.5
        assert stats.average == 1.5

    def test_add_multiple_values(self) -> None:
        """Test adding multiple values."""
        stats = ResponseTimeStats()
        stats.add(1.0)
        stats.add(2.0)
        stats.add(3.0)
        assert len(stats.times) == 3
        assert stats._sum == 6.0
        assert stats.average == 2.0

    def test_average_empty(self) -> None:
        """Test average returns 0.0 when empty."""
        stats = ResponseTimeStats()
        assert stats.average == 0.0

    def test_count_property(self) -> None:
        """Test count property returns correct length."""
        stats = ResponseTimeStats()
        assert stats.count == 0
        stats.add(1.0)
        stats.add(2.0)
        assert stats.count == 2

    def test_clear_resets_all(self) -> None:
        """Test clear resets times and sum."""
        stats = ResponseTimeStats()
        stats.add(1.0)
        stats.add(2.0)
        stats.clear()
        assert stats.count == 0
        assert stats._sum == 0.0
        assert stats.average == 0.0

    def test_circular_buffer_eviction(self) -> None:
        """Test that old values are evicted and sum is updated correctly."""
        # Create stats with small maxlen for testing
        stats = ResponseTimeStats()
        stats.times = deque(maxlen=3)  # Override for testing

        stats.add(1.0)
        stats.add(2.0)
        stats.add(3.0)
        assert stats._sum == 6.0
        assert stats.average == 2.0

        # Adding 4th value should evict 1.0
        stats.add(4.0)
        assert len(stats.times) == 3
        assert list(stats.times) == [2.0, 3.0, 4.0]
        assert stats._sum == 9.0  # 2 + 3 + 4
        assert stats.average == 3.0

    def test_o1_average_calculation(self) -> None:
        """Test that average is O(1) using pre-calculated sum."""
        stats = ResponseTimeStats()
        # Add many values
        for i in range(100):
            stats.add(float(i))

        # Average of 0-99 is 49.5
        assert stats.average == 49.5


class TestMetricsManager:
    """Tests for MetricsManager class."""

    def test_init(self) -> None:
        """Test MetricsManager initialization."""
        manager = MetricsManager()
        assert manager._cache_hits == 0
        assert manager._cache_misses == 0
        assert manager._circuit_breaker_opens == 0
        assert manager._rate_limit_hits == 0

    def test_record_request(self) -> None:
        """Test recording API requests."""
        manager = MetricsManager()
        manager.record_request("/api/test")
        manager.record_request("/api/test")
        manager.record_request("/api/other")

        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/test"] == 2
        assert metrics["request_counts"]["/api/other"] == 1

    def test_record_error(self) -> None:
        """Test recording API errors."""
        manager = MetricsManager()
        manager.record_error("/api/test")

        metrics = manager.get_metrics()
        assert metrics["error_counts"]["/api/test"] == 1

    def test_record_response_time(self) -> None:
        """Test recording response times."""
        manager = MetricsManager()
        manager.record_response_time("/api/test", 0.5)
        manager.record_response_time("/api/test", 0.3)

        metrics = manager.get_metrics()
        assert metrics["avg_response_times"]["/api/test"] == 0.4

    def test_record_ai_request(self) -> None:
        """Test recording AI requests."""
        manager = MetricsManager()
        manager.record_ai_request("itinerary")
        manager.record_ai_request("query")
        manager.record_ai_request("itinerary")

        metrics = manager.get_metrics()
        assert metrics["ai_request_counts"]["itinerary"] == 2
        assert metrics["ai_request_counts"]["query"] == 1

    def test_record_cache_hit(self) -> None:
        """Test recording cache hits."""
        manager = MetricsManager()
        manager.record_cache_hit()
        manager.record_cache_hit()

        metrics = manager.get_metrics()
        assert metrics["cache_stats"]["hits"] == 2

    def test_record_cache_miss(self) -> None:
        """Test recording cache misses."""
        manager = MetricsManager()
        manager.record_cache_miss()

        metrics = manager.get_metrics()
        assert metrics["cache_stats"]["misses"] == 1

    def test_cache_hit_rate_calculation(self) -> None:
        """Test cache hit rate calculation."""
        manager = MetricsManager()
        manager.record_cache_hit()
        manager.record_cache_hit()
        manager.record_cache_miss()
        manager.record_cache_miss()

        metrics = manager.get_metrics()
        assert metrics["cache_stats"]["hit_rate"] == "50.00%"

    def test_cache_hit_rate_zero_requests(self) -> None:
        """Test cache hit rate with no requests."""
        manager = MetricsManager()
        metrics = manager.get_metrics()
        assert metrics["cache_stats"]["hit_rate"] == "0.00%"

    def test_record_circuit_breaker_open(self) -> None:
        """Test recording circuit breaker opens."""
        manager = MetricsManager()
        manager.record_circuit_breaker_open()

        metrics = manager.get_metrics()
        assert metrics["circuit_breaker_opens"] == 1

    def test_record_rate_limit_hit(self) -> None:
        """Test recording rate limit hits."""
        manager = MetricsManager()
        manager.record_rate_limit_hit()
        manager.record_rate_limit_hit()

        metrics = manager.get_metrics()
        assert metrics["rate_limit_hits"] == 2

    def test_reset_metrics(self) -> None:
        """Test resetting all metrics."""
        manager = MetricsManager()
        manager.record_request("/api/test")
        manager.record_error("/api/test")
        manager.record_response_time("/api/test", 0.5)
        manager.record_ai_request("query")
        manager.record_cache_hit()
        manager.record_cache_miss()
        manager.record_circuit_breaker_open()
        manager.record_rate_limit_hit()

        manager.reset_metrics()

        metrics = manager.get_metrics()
        assert metrics["request_counts"] == {}
        assert metrics["error_counts"] == {}
        assert metrics["avg_response_times"] == {}
        assert metrics["ai_request_counts"] == {}
        assert metrics["cache_stats"]["hits"] == 0
        assert metrics["cache_stats"]["misses"] == 0
        assert metrics["circuit_breaker_opens"] == 0
        assert metrics["rate_limit_hits"] == 0

    def test_thread_safety(self) -> None:
        """Test thread safety of MetricsManager."""
        manager = MetricsManager()
        iterations = 100

        def record_requests() -> None:
            for _ in range(iterations):
                manager.record_request("/api/test")

        def record_errors() -> None:
            for _ in range(iterations):
                manager.record_error("/api/test")

        threads = [
            Thread(target=record_requests),
            Thread(target=record_requests),
            Thread(target=record_errors),
            Thread(target=record_errors),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/test"] == iterations * 2
        assert metrics["error_counts"]["/api/test"] == iterations * 2

    def test_get_metrics_returns_copy(self) -> None:
        """Test that get_metrics returns a copy, not references."""
        manager = MetricsManager()
        manager.record_request("/api/test")

        metrics1 = manager.get_metrics()
        metrics1["request_counts"]["/api/test"] = 999

        metrics2 = manager.get_metrics()
        assert metrics2["request_counts"]["/api/test"] == 1


class TestRequestTimer:
    """Tests for RequestTimer context manager."""

    def test_sync_context_manager(self) -> None:
        """Test RequestTimer as sync context manager."""
        manager = MetricsManager()

        with RequestTimer("/api/test", manager) as timer:
            sleep(0.01)

        assert timer.elapsed > 0.01
        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/test"] == 1
        assert "/api/test" in metrics["avg_response_times"]

    def test_sync_context_manager_with_exception(self) -> None:
        """Test RequestTimer records error on exception."""
        manager = MetricsManager()

        with pytest.raises(ValueError), RequestTimer("/api/test", manager):
            raise ValueError("error")

        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/test"] == 1
        assert metrics["error_counts"]["/api/test"] == 1

    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """Test RequestTimer as async context manager."""
        manager = MetricsManager()

        async with RequestTimer("/api/async", manager) as timer:
            await async_sleep(0.01)

        assert timer.elapsed > 0.01
        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/async"] == 1

    @pytest.mark.asyncio
    async def test_async_context_manager_with_exception(self) -> None:
        """Test async RequestTimer records error on exception."""
        manager = MetricsManager()

        with pytest.raises(ValueError):
            async with RequestTimer("/api/async", manager):
                raise ValueError("error")

        metrics = manager.get_metrics()
        assert metrics["error_counts"]["/api/async"] == 1

    def test_elapsed_before_exit(self) -> None:
        """Test elapsed property during context."""
        manager = MetricsManager()

        with RequestTimer("/api/test", manager) as timer:
            sleep(0.01)
            elapsed_during = timer.elapsed
            assert elapsed_during > 0.01

    def test_elapsed_before_enter(self) -> None:
        """Test elapsed returns 0 before entering context."""
        timer = RequestTimer("/api/test")
        assert timer.elapsed == 0.0

    def test_default_metrics_manager(self) -> None:
        """Test RequestTimer uses global metrics_manager by default."""
        initial_count = metrics_manager.get_metrics()["request_counts"].get("/api/default", 0)

        with RequestTimer("/api/default"):
            pass

        new_count = metrics_manager.get_metrics()["request_counts"].get("/api/default", 0)
        assert new_count == initial_count + 1


class TestTimedDecorator:
    """Tests for @timed decorator."""

    @pytest.mark.asyncio
    async def test_timed_decorator_records_metrics(self) -> None:
        """Test that @timed decorator records request and response time."""
        manager = MetricsManager()

        @timed("/api/decorated", manager)
        async def decorated_function() -> str:
            await async_sleep(0.01)
            return "success"

        result = await decorated_function()

        assert result == "success"
        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/decorated"] == 1
        assert "/api/decorated" in metrics["avg_response_times"]

    @pytest.mark.asyncio
    async def test_timed_decorator_uses_function_name(self) -> None:
        """Test that @timed uses function name when endpoint not provided."""
        manager = MetricsManager()

        @timed(metrics=manager)
        async def my_endpoint_function() -> str:
            return "ok"

        await my_endpoint_function()

        metrics = manager.get_metrics()
        assert metrics["request_counts"]["my_endpoint_function"] == 1

    @pytest.mark.asyncio
    async def test_timed_decorator_records_error(self) -> None:
        """Test that @timed decorator records errors."""
        manager = MetricsManager()

        @timed("/api/error", manager)
        async def error_function() -> None:
            raise ValueError("error")

        with pytest.raises(ValueError):
            await error_function()

        metrics = manager.get_metrics()
        assert metrics["request_counts"]["/api/error"] == 1
        assert metrics["error_counts"]["/api/error"] == 1

    @pytest.mark.asyncio
    async def test_timed_decorator_preserves_function_metadata(self) -> None:
        """Test that @timed preserves function metadata via @wraps."""
        manager = MetricsManager()

        @timed("/api/test", manager)
        async def documented_function() -> str:
            """Return ok string."""
            return "ok"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "Return ok string."


class TestSystemMetrics:
    """Tests for SystemMetrics dataclass."""

    def test_system_metrics_is_frozen(self) -> None:
        """Test that SystemMetrics is immutable (frozen dataclass)."""
        metrics = SystemMetrics(
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=8000.0,
            memory_total_mb=16000.0,
            disk_percent=40.0,
        )

        with pytest.raises(AttributeError):
            metrics.cpu_percent = 100.0  # type: ignore[misc]

    def test_system_metrics_to_dict(self) -> None:
        """Test SystemMetrics to_dict method."""
        metrics = SystemMetrics(
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=8000.0,
            memory_total_mb=16000.0,
            disk_percent=40.0,
        )

        result = metrics.to_dict()

        assert result["cpu_percent"] == 50.0
        assert result["memory"]["percent"] == 60.0
        assert result["memory"]["used_mb"] == 8000.0
        assert result["memory"]["total_mb"] == 16000.0
        assert result["disk_percent"] == 40.0


class TestGetSystemMetrics:
    """Tests for get_system_metrics async function."""

    @pytest.mark.asyncio
    async def test_get_system_metrics_returns_dict(self) -> None:
        """Test that get_system_metrics returns a dictionary."""
        result = await get_system_metrics()

        assert isinstance(result, dict)
        assert "cpu_percent" in result
        assert "memory" in result
        assert "disk_percent" in result

    @pytest.mark.asyncio
    async def test_get_system_metrics_memory_structure(self) -> None:
        """Test memory info structure in result."""
        result = await get_system_metrics()

        memory = result["memory"]
        assert "percent" in memory
        assert "used_mb" in memory
        assert "total_mb" in memory

    @pytest.mark.asyncio
    async def test_get_system_metrics_values_are_numeric(self) -> None:
        """Test that all metric values are numeric."""
        result = await get_system_metrics()

        assert isinstance(result["cpu_percent"], (int, float))
        assert isinstance(result["memory"]["percent"], (int, float))
        assert isinstance(result["memory"]["used_mb"], (int, float))
        assert isinstance(result["memory"]["total_mb"], (int, float))
        assert isinstance(result["disk_percent"], (int, float))

    @pytest.mark.asyncio
    async def test_get_system_metrics_handles_oserror(self) -> None:
        """Test that get_system_metrics handles OSError gracefully."""
        with patch("app.managers.metrics.get_cpu_percent", side_effect=OSError("Test")):
            result = await get_system_metrics()

            assert "error" in result
            assert "Test" in result["error"]

    @pytest.mark.asyncio
    async def test_get_system_metrics_uses_asyncio_to_thread(self) -> None:
        """Test that blocking calls are run in thread pool."""
        with patch("app.managers.metrics.to_thread") as mock_to_thread:
            # Create a mock future that returns proper values
            mock_to_thread.return_value = SystemMetrics(
                cpu_percent=50.0,
                memory_percent=60.0,
                memory_used_mb=8000.0,
                memory_total_mb=16000.0,
                disk_percent=40.0,
            )

            result = await get_system_metrics()

            mock_to_thread.assert_called_once()
            assert result["cpu_percent"] == 50.0
