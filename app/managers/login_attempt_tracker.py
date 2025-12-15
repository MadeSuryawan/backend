"""Login attempt tracker for brute-force protection using Redis."""

from logging import getLogger

from redis.exceptions import RedisError

from app.clients.redis_client import RedisClient
from app.configs import settings
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))

# Key prefixes for login attempts
ATTEMPTS_PREFIX = "login:attempts:"
LOCKOUT_PREFIX = "login:lockout:"


class LoginAttemptTracker:
    """
    Track failed login attempts in Redis with exponential backoff.

    Implements account lockout after configurable number of failed attempts.
    Uses exponential backoff for repeat offenders.
    """

    def __init__(self, redis_client: RedisClient) -> None:
        """
        Initialize the login attempt tracker.

        Args:
            redis_client: Redis client instance for storage
        """
        self._redis = redis_client
        self._max_attempts = settings.MAX_LOGIN_ATTEMPTS
        self._lockout_duration = settings.LOCKOUT_DURATION_MINUTES * 60  # Convert to seconds

    def _get_attempts_key(self, identifier: str) -> str:
        """Get Redis key for attempt count."""
        return f"{ATTEMPTS_PREFIX}{identifier}"

    def _get_lockout_key(self, identifier: str) -> str:
        """Get Redis key for lockout status."""
        return f"{LOCKOUT_PREFIX}{identifier}"

    async def record_failed_attempt(self, identifier: str) -> int:
        """
        Record a failed login attempt.

        Args:
            identifier: User identifier (username, email, or IP)

        Returns:
            int: Current number of failed attempts
        """
        try:
            key = self._get_attempts_key(identifier)

            # Get current count
            current = await self._redis.get(key)
            attempts = int(current) + 1 if current else 1

            # Store updated count with expiration
            await self._redis.set(key, str(attempts), ex=self._lockout_duration)

            # Check if we should trigger lockout
            if attempts >= self._max_attempts:
                await self._trigger_lockout(identifier, attempts)

            logger.debug(
                "Failed login attempt %d/%d for %s",
                attempts,
                self._max_attempts,
                identifier,
            )
            return attempts
        except RedisError:
            logger.exception("Failed to record login attempt for %s", identifier)
            return 0

    async def _trigger_lockout(self, identifier: str, attempts: int) -> None:
        """
        Trigger account lockout with exponential backoff.

        Args:
            identifier: User identifier
            attempts: Current attempt count
        """
        try:
            lockout_key = self._get_lockout_key(identifier)

            # Calculate lockout duration with exponential backoff
            # Base: 15 min, then 30 min, 60 min, etc.
            multiplier = max(1, (attempts - self._max_attempts) // self._max_attempts + 1)
            lockout_seconds = self._lockout_duration * multiplier

            # Cap at 24 hours
            lockout_seconds = min(lockout_seconds, 86400)

            await self._redis.set(lockout_key, str(lockout_seconds), ex=lockout_seconds)
            logger.warning(
                "Account locked for %s: %d seconds (attempt %d)",
                identifier,
                lockout_seconds,
                attempts,
            )
        except RedisError:
            logger.exception("Failed to trigger lockout for %s", identifier)

    async def is_locked_out(self, identifier: str) -> tuple[bool, int]:
        """
        Check if an identifier is locked out.

        Args:
            identifier: User identifier to check

        Returns:
            tuple[bool, int]: (is_locked, seconds_remaining)
        """
        try:
            lockout_key = self._get_lockout_key(identifier)
            ttl = await self._redis.ttl(lockout_key)

            if ttl > 0:
                return (True, ttl)
            return (False, 0)
        except RedisError:
            logger.exception("Failed to check lockout for %s", identifier)
            # Fail open - don't lock out if we can't check
            return (False, 0)

    async def reset_attempts(self, identifier: str) -> bool:
        """
        Reset failed attempts after successful login.

        Args:
            identifier: User identifier

        Returns:
            bool: True if successfully reset
        """
        try:
            attempts_key = self._get_attempts_key(identifier)
            lockout_key = self._get_lockout_key(identifier)

            await self._redis.delete(attempts_key, lockout_key)
            logger.debug("Reset login attempts for %s", identifier)
            return True
        except RedisError:
            logger.exception("Failed to reset attempts for %s", identifier)
            return False

    async def get_attempts_count(self, identifier: str) -> int:
        """
        Get current failed attempt count.

        Args:
            identifier: User identifier

        Returns:
            int: Number of failed attempts
        """
        try:
            key = self._get_attempts_key(identifier)
            current = await self._redis.get(key)
            return int(current) if current else 0
        except RedisError:
            logger.exception("Failed to get attempts for %s", identifier)
            return 0


# Global instance - initialized in app startup
_login_tracker: LoginAttemptTracker | None = None


def get_login_tracker() -> LoginAttemptTracker:
    """
    Get the global login attempt tracker instance.

    Returns:
        LoginAttemptTracker: The global tracker instance

    Raises:
        RuntimeError: If tracker not initialized
    """
    if _login_tracker is None:
        msg = "Login tracker not initialized. Call init_login_tracker() first."
        raise RuntimeError(msg)
    return _login_tracker


def init_login_tracker(redis_client: RedisClient) -> LoginAttemptTracker:
    """
    Initialize the global login attempt tracker.

    Args:
        redis_client: Redis client to use for storage

    Returns:
        LoginAttemptTracker: The initialized tracker instance
    """
    global _login_tracker  # noqa: PLW0603
    _login_tracker = LoginAttemptTracker(redis_client)
    logger.info("Login attempt tracker initialized")
    return _login_tracker
