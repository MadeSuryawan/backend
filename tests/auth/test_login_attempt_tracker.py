"""Tests for the login attempt tracker (brute-force protection)."""

from unittest.mock import AsyncMock, MagicMock

from pytest import mark

from app.managers.login_attempt_tracker import LoginAttemptTracker


class TestLoginAttemptTracker:
    """Test cases for LoginAttemptTracker class."""

    @mark.asyncio
    async def test_record_failed_attempt_increments_count(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test that failed attempts are recorded and incremented."""
        mock_redis_client.get = AsyncMock(return_value=None)  # First attempt
        identifier = "testuser"

        attempts = await login_tracker.record_failed_attempt(identifier)

        assert attempts == 1
        mock_redis_client.set.assert_called()

    @mark.asyncio
    async def test_record_failed_attempt_increments_existing(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test that existing attempt count is incremented."""
        mock_redis_client.get = AsyncMock(return_value="2")  # Already 2 attempts
        identifier = "testuser"

        attempts = await login_tracker.record_failed_attempt(identifier)

        assert attempts == 3

    @mark.asyncio
    async def test_is_locked_out_returns_false_when_not_locked(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test is_locked_out returns False when user is not locked."""
        mock_redis_client.ttl = AsyncMock(return_value=-2)  # Key doesn't exist
        identifier = "testuser"

        is_locked, seconds = await login_tracker.is_locked_out(identifier)

        assert is_locked is False
        assert seconds == 0

    @mark.asyncio
    async def test_is_locked_out_returns_true_when_locked(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test is_locked_out returns True when user is locked."""
        mock_redis_client.ttl = AsyncMock(return_value=600)  # 10 minutes left
        identifier = "testuser"

        is_locked, seconds = await login_tracker.is_locked_out(identifier)

        assert is_locked is True
        assert seconds == 600

    @mark.asyncio
    async def test_reset_attempts_clears_data(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test that reset_attempts clears attempt count and lockout."""
        identifier = "testuser"

        result = await login_tracker.reset_attempts(identifier)

        assert result is True
        mock_redis_client.delete.assert_called_once()

    @mark.asyncio
    async def test_get_attempts_count_returns_zero_when_none(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_attempts_count returns 0 when no attempts recorded."""
        mock_redis_client.get = AsyncMock(return_value=None)
        identifier = "testuser"

        count = await login_tracker.get_attempts_count(identifier)

        assert count == 0

    @mark.asyncio
    async def test_get_attempts_count_returns_correct_value(
        self,
        login_tracker: LoginAttemptTracker,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test get_attempts_count returns correct value."""
        mock_redis_client.get = AsyncMock(return_value="5")
        identifier = "testuser"

        count = await login_tracker.get_attempts_count(identifier)

        assert count == 5

    def test_key_prefixes_are_correct(
        self,
        login_tracker: LoginAttemptTracker,
    ) -> None:
        """Test that key prefixes are correctly applied."""
        identifier = "testuser"

        attempts_key = login_tracker._get_attempts_key(identifier)
        lockout_key = login_tracker._get_lockout_key(identifier)

        assert attempts_key == f"login:attempts:{identifier}"
        assert lockout_key == f"login:lockout:{identifier}"
