"""Token blacklist manager for JWT revocation using Redis."""

from datetime import UTC, datetime
from logging import getLogger

from redis.exceptions import RedisError

from app.clients.redis_client import RedisClient
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

# Key prefix for blacklisted tokens
BLACKLIST_PREFIX = "token:blacklist:"


class TokenBlacklist:
    """
    Redis-backed token blacklist with TTL matching token expiration.

    Tokens are stored with their JTI (JWT ID) as the key and automatically
    expire from Redis when the original token would have expired.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        """
        Initialize the token blacklist.

        Args:
            redis_client: Redis client instance for storage
        """
        self._redis = redis_client

    def _get_key(self, jti: str) -> str:
        """
        Generate Redis key for a token JTI.

        Args:
            jti: JWT ID

        Returns:
            str: Redis key
        """
        return f"{BLACKLIST_PREFIX}{jti}"

    async def add_to_blacklist(self, jti: str, exp: datetime) -> bool:
        """
        Add a token to the blacklist.

        Args:
            jti: JWT ID to blacklist
            exp: Token expiration time (used to calculate TTL)

        Returns:
            bool: True if successfully added
        """
        try:
            key = self._get_key(jti)
            now = datetime.now(UTC)

            # Calculate TTL based on token expiration
            ttl_seconds = int((exp - now).total_seconds())

            if ttl_seconds <= 0:
                # Token already expired, no need to blacklist
                logger.debug("Token %s already expired, skipping blacklist", jti)
                return True

            # Store with TTL so it auto-expires
            result = await self._redis.set(key, "1", ex=ttl_seconds)
            logger.debug("Token %s blacklisted with TTL %d seconds", jti, ttl_seconds)
            return result
        except RedisError:
            logger.exception("Failed to blacklist token %s", jti)
            return False

    async def is_blacklisted(self, jti: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            jti: JWT ID to check

        Returns:
            bool: True if token is blacklisted
        """
        try:
            key = self._get_key(jti)
            exists = await self._redis.exists(key)
            return exists > 0
        except RedisError:
            logger.exception("Failed to check blacklist for token %s", jti)
            # Fail closed - treat as blacklisted if we can't check
            return True

    async def remove_from_blacklist(self, jti: str) -> bool:
        """
        Remove a token from the blacklist (rarely needed).

        Args:
            jti: JWT ID to remove

        Returns:
            bool: True if successfully removed
        """
        try:
            key = self._get_key(jti)
            deleted = await self._redis.delete(key)
            return deleted > 0
        except RedisError:
            logger.exception("Failed to remove token %s from blacklist", jti)
            return False

    async def get_blacklist_count(self) -> int:
        """
        Get the count of blacklisted tokens (for monitoring).

        Returns:
            int: Number of blacklisted tokens
        """
        try:
            count = 0
            async for _ in self._redis.scan_iter(f"{BLACKLIST_PREFIX}*"):
                count += 1
            return count
        except RedisError:
            logger.exception("Failed to count blacklisted tokens")
            return -1


# Global instance - initialized in app startup
_token_blacklist: TokenBlacklist | None = None


def get_token_blacklist() -> TokenBlacklist:
    """
    Get the global token blacklist instance.

    Returns:
        TokenBlacklist: The global blacklist instance

    Raises:
        RuntimeError: If blacklist not initialized
    """
    if _token_blacklist is None:
        msg = "Token blacklist not initialized. Call init_token_blacklist() first."
        raise RuntimeError(msg)
    return _token_blacklist


def init_token_blacklist(redis_client: RedisClient) -> TokenBlacklist:
    """
    Initialize the global token blacklist.

    Args:
        redis_client: Redis client to use for storage

    Returns:
        TokenBlacklist: The initialized blacklist instance
    """
    global _token_blacklist  # noqa: PLW0603
    _token_blacklist = TokenBlacklist(redis_client)
    logger.info("Token blacklist initialized")
    return _token_blacklist
