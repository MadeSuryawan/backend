"""Tests for the Redis-backed token blacklist."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from pytest import mark

from app.managers.token_blacklist import TokenBlacklist


class TestTokenBlacklist:
    """Test cases for TokenBlacklist class."""

    @mark.asyncio
    async def test_add_to_blacklist_success(
        self,
        token_blacklist: TokenBlacklist,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test adding a token to the blacklist."""
        jti = "test-jti-123"
        exp = datetime.now(UTC) + timedelta(hours=1)

        result = await token_blacklist.add_to_blacklist(jti, exp)

        assert result is True
        mock_redis_client.set.assert_called_once()

    @mark.asyncio
    async def test_add_expired_token_skipped(
        self,
        token_blacklist: TokenBlacklist,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test that already expired tokens are not added."""
        jti = "test-jti-123"
        exp = datetime.now(UTC) - timedelta(hours=1)  # Already expired

        result = await token_blacklist.add_to_blacklist(jti, exp)

        assert result is True
        mock_redis_client.set.assert_not_called()

    @mark.asyncio
    async def test_is_blacklisted_returns_false_when_not_found(
        self,
        token_blacklist: TokenBlacklist,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test is_blacklisted returns False when token not in blacklist."""
        mock_redis_client.exists = AsyncMock(return_value=0)
        jti = "test-jti-123"

        result = await token_blacklist.is_blacklisted(jti)

        assert result is False

    @mark.asyncio
    async def test_is_blacklisted_returns_true_when_found(
        self,
        token_blacklist: TokenBlacklist,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test is_blacklisted returns True when token is in blacklist."""
        mock_redis_client.exists = AsyncMock(return_value=1)
        jti = "test-jti-123"

        result = await token_blacklist.is_blacklisted(jti)

        assert result is True

    @mark.asyncio
    async def test_remove_from_blacklist(
        self,
        token_blacklist: TokenBlacklist,
        mock_redis_client: MagicMock,
    ) -> None:
        """Test removing a token from the blacklist."""
        jti = "test-jti-123"

        result = await token_blacklist.remove_from_blacklist(jti)

        assert result is True
        mock_redis_client.delete.assert_called_once()

    @mark.asyncio
    async def test_key_prefix_is_correct(
        self,
        token_blacklist: TokenBlacklist,
    ) -> None:
        """Test that the key prefix is correctly applied."""
        jti = "test-jti"
        expected_key = f"token:blacklist:{jti}"

        key = token_blacklist._get_key(jti)

        assert key == expected_key
