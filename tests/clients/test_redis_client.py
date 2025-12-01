"""Tests for app/clients/redis_client.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.clients.redis_client import (
    RETRIABLE_EXCEPTIONS,
    RedisClient,
)
from app.decorators import _log_before_sleep, with_retry


class TestBeforeSleepCallback:
    """Tests for _log_before_sleep function."""

    def test_callback_creation(self) -> None:
        """Test that callback is created successfully."""
        callback = _log_before_sleep(3)
        assert callable(callback)

    def test_callback_logs_retry_info(self) -> None:
        """Test that callback logs retry information."""
        callback = _log_before_sleep(3)

        # Create mock retry state
        retry_state = MagicMock()
        retry_state.attempt_number = 1
        retry_state.outcome = MagicMock()
        retry_state.outcome.exception.return_value = RedisConnectionError("Test")
        retry_state.next_action = MagicMock()
        retry_state.next_action.sleep = 0.5
        retry_state.fn = MagicMock()
        retry_state.fn.__name__ = "test_func"

        # Should not raise
        callback(retry_state)

    def test_callback_handles_no_next_action(self) -> None:
        """Test callback handles missing next_action."""
        callback = _log_before_sleep(3)

        retry_state = MagicMock()
        retry_state.attempt_number = 1
        retry_state.outcome = MagicMock()
        retry_state.outcome.exception.return_value = None
        retry_state.next_action = None
        retry_state.fn = None

        # Should not raise
        callback(retry_state)


class TestWithRetryDecorator:
    """Tests for with_retry decorator."""

    def test_decorator_returns_callable(self) -> None:
        """Test that decorator returns a callable."""
        decorator = with_retry(max_retries=3)
        assert callable(decorator)

    @pytest.mark.asyncio
    async def test_decorated_function_success(self) -> None:
        """Test decorated function executes successfully."""

        @with_retry(max_retries=2)
        async def success_func() -> str:
            return "success"

        result = await success_func()
        assert result == "success"


class TestRetriableExceptions:
    """Tests for RETRIABLE_EXCEPTIONS constant."""

    def test_includes_redis_connection_error(self) -> None:
        """Test that RedisConnectionError is in retriable exceptions."""
        assert RedisConnectionError in RETRIABLE_EXCEPTIONS

    def test_includes_timeout_errors(self) -> None:
        """Test that timeout errors are in retriable exceptions."""
        assert TimeoutError in RETRIABLE_EXCEPTIONS
        assert ConnectionError in RETRIABLE_EXCEPTIONS


class TestRedisClientInit:
    """Tests for RedisClient initialization."""

    def test_init_default_state(self) -> None:
        """Test that RedisClient initializes with correct default state."""
        client = RedisClient()
        assert client._pool is None
        assert client._redis is None
        assert client.config is not None


class TestRedisClientConnect:
    """Tests for RedisClient connect method."""

    @pytest.mark.asyncio
    @patch("app.clients.redis_client.ConnectionPool")
    @patch("app.clients.redis_client.Redis")
    async def test_connect_success(
        self,
        mock_redis: MagicMock,
        mock_pool: MagicMock,
    ) -> None:
        """Test successful connection."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping = AsyncMock(return_value=True)
        mock_redis.return_value = mock_redis_instance

        client = RedisClient()
        await client.connect()

        assert client._pool is not None
        assert client._redis is not None

    @pytest.mark.asyncio
    @patch("app.clients.redis_client.ConnectionPool")
    @patch("app.clients.redis_client.Redis")
    async def test_connect_ping_fails(
        self,
        mock_redis: MagicMock,
        mock_pool: MagicMock,
    ) -> None:
        """Test connection failure when ping returns False."""
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping = AsyncMock(return_value=False)
        mock_redis.return_value = mock_redis_instance

        client = RedisClient()
        with pytest.raises(RedisConnectionError):
            await client.connect()


class TestRedisClientDisconnect:
    """Tests for RedisClient disconnect method."""

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnect when not connected doesn't raise."""
        client = RedisClient()
        await client.disconnect()
        assert client._redis is None
        assert client._pool is None

    @pytest.mark.asyncio
    async def test_disconnect_closes_resources(self) -> None:
        """Test disconnect properly closes resources."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_pool = AsyncMock()
        client._redis = mock_redis
        client._pool = mock_pool

        await client.disconnect()

        mock_redis.close.assert_called_once()
        mock_pool.disconnect.assert_called_once()
        assert client._redis is None
        assert client._pool is None


class TestRedisClientProperty:
    """Tests for RedisClient client property."""

    def test_client_raises_when_not_initialized(self) -> None:
        """Test that accessing client before connect raises RuntimeError."""
        redis_client = RedisClient()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = redis_client.client


class TestRedisClientOperations:
    """Tests for RedisClient cache operations."""

    @pytest.mark.asyncio
    async def test_delete_empty_keys(self) -> None:
        """Test delete with no keys returns 0."""
        client = RedisClient()
        mock_redis = AsyncMock()
        client._redis = mock_redis

        result = await client.delete()
        assert result == 0


class TestRedisHealthCheck:
    """Tests for RedisClient health_check method."""

    @pytest.mark.asyncio
    async def test_health_check_success(self) -> None:
        """Test health check returns proper structure on success."""
        client = RedisClient()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.info = AsyncMock(
            return_value={
                "connected_clients": 5,
                "used_memory_human": "1M",
                "uptime_in_seconds": 3600,
                "redis_version": "7.0.0",
            },
        )
        client._redis = mock_redis

        result = await client.health_check()

        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert result["connected_clients"] == 5

    @pytest.mark.asyncio
    async def test_health_check_failure(self) -> None:
        """Test health check returns unhealthy on error."""
        client = RedisClient()
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock(side_effect=RedisError("Connection lost"))
        client._redis = mock_redis

        result = await client.health_check()

        assert result["status"] == "unhealthy"
        assert "error" in result
