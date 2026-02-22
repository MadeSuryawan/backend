"""
Password hashing module using Argon2 with passlib's CryptContext.

This module provides secure password hashing and verification using Argon2id,
which is considered one of the most secure password hashing algorithms available.
"""

from asyncio import get_event_loop
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar

from passlib.context import CryptContext
from passlib.exc import InternalBackendError

from app.configs import CONFIG_MAP, settings
from app.decorators.with_retry import with_retry
from app.errors import PasswordHashingError, PasswordRehashError
from app.monitoring import get_logger

executor = ThreadPoolExecutor(max_workers=4)
logger = get_logger(__name__)


class PasswordHasher:
    """
    A secure password hashing and verification manager using Argon2id algorithm.

    This class wraps passlib's CryptContext to provide:
    - Secure password hashing with Argon2id
    - Password verification
    - Hash deprecation checking and rehashing capabilities
    """

    def __init__(self) -> None:
        """
        Initialize the PasswordHasher with Argon2id as the primary scheme.

        Configuration:
        - schemes: List of supported hashing schemes (argon2 as primary)
        - deprecated: List of deprecated schemes for automatic migration
        - argon2__memory_cost: Memory usage (default: 512MB for security)
        - argon2__time_cost: Time cost/iterations (default: 2)
        - argon2__parallelism: Parallelism factor (default: 2 threads)
        """

        self.request_id = ContextVar("request_id", default="")
        self.level = settings.PASSWORD_SECURITY_LEVEL
        self.pwd_context = CryptContext(
            schemes=[
                "argon2",
                "pbkdf2_sha256",
            ],  # argon2 as primary, pbkdf2 for fallback
            deprecated="pbkdf2_sha256",  # Mark pbkdf2 as deprecated for auto-migration
            # Argon2id specific parameters
            argon2__memory_cost=CONFIG_MAP[self.level].memory_cost,
            argon2__time_cost=CONFIG_MAP[self.level].time_cost,
            argon2__parallelism=CONFIG_MAP[self.level].parallelism,
        )
        logger.info(f"PasswordHasher initialized with Argon2id on level {self.level}")

    def hash(self, password: str) -> str:
        """
        Hash a plaintext password using Argon2id.

        Args:
            password: The plaintext password to hash

        Returns:
            str: The hashed password in Argon2id format

        Raises:
            ValueError: If password is empty or invalid
            PasswordHashingError: If hashing fails

        Example:
            >>> hasher = PasswordHasher()
            >>> hashed = hasher.hash("my_secure_password")
            >>> print(hashed)  # $argon2id$v=19$m=524288,t=2,p=2$...
        """
        if not password:
            msg = "Password cannot be empty"
            raise ValueError(msg) from None

        try:
            hashed_password = self.pwd_context.hash(password)
            logger.debug(f"Password hashed successfully on level {self.level}")
        except (ValueError, InternalBackendError, UnicodeError) as e:
            logger.exception("Invalid password format")
            mssg = "Failed to hash password"
            raise PasswordHashingError(mssg) from e
        except Exception as e:
            logger.exception("Error hashing password")
            mssg = "Failed to hash password"
            raise PasswordHashingError(mssg) from e
        return hashed_password

    def verify(self, password: str, hashed_password: str) -> bool:
        """
        Verify a plaintext password against a hashed password.

        Args:
            password: The plaintext password to verify
            hashed_password: The hashed password to verify against

        Returns:
            bool: True if password matches, False otherwise

        Example:
            >>> hasher = PasswordHasher()
            >>> hashed = hasher.hash("my_password")
            >>> hasher.verify("my_password", hashed)
            True
            >>> hasher.verify("wrong_password", hashed)
            False
        """
        if not isinstance(hashed_password, str) or not hashed_password.strip():
            logger.warning("Invalid hash format provided")
            return False

        try:
            is_valid = self.pwd_context.verify(password, hashed_password)
        except ValueError:
            logger.exception("Stored hash is corrupted or invalid format")
            return False  # Or raise, depending on policy
        except Exception:
            logger.exception("Unexpected error during verification")
            return False

        return is_valid

    def check_needs_rehash(self, hashed_password: str) -> bool:
        """
        Check if a hashed password needs to be rehashed due to deprecated scheme or outdated parameters.

        Args:
            hashed_password: The hashed password to check

        Returns:
            bool: True if rehashing is needed, False otherwise

        Example:
            >>> hasher = PasswordHasher()
            >>> old_pbkdf2_hash = "$pbkdf2-sha256$..."
            >>> hasher.check_needs_rehash(old_pbkdf2_hash)
            True
        """
        try:
            needs_rehash = self.pwd_context.needs_update(hashed_password)
            if needs_rehash:
                logger.info(
                    f"Hash needs update due to deprecated scheme or outdated parameters on level {self.level}",
                )
        except Exception:
            logger.exception(f"Error checking hash currency on level {self.level}")
            return False

        return needs_rehash

    def verify_and_update(
        self,
        password: str,
        hashed_password: str | None,
    ) -> tuple[bool, str | None]:
        """
        Verify a password and return a new hash if the current one needs updating.

        This is useful for authentication flows where you want to automatically
        upgrade old password hashes to the current security standard.

        Args:
            password: The plaintext password to verify
            hashed_password: The hashed password (can be None for missing passwords)

        Returns:
            tuple[bool, Optional[str]]:
                - First element: True if password is correct, False otherwise
                - Second element: New hash if rehashing needed, None otherwise

        Example:
            >>> hasher = PasswordHasher()
            >>> hashed = hasher.hash("password123")
            >>> is_valid, new_hash = hasher.verify_and_update("password123", hashed)
            >>> if is_valid:
            ...     if new_hash:
            ...         # Update database with new_hash
            ...         db.update_password_hash(user_id, new_hash)
        """
        if hashed_password is None:
            logger.warning(
                "Hashed password is None, using dummy hash for timing consistency",
            )
            # Use dummy_verify() to maintain timing consistency against timing attacks
            self.pwd_context.dummy_verify()
            return False, None

        # Verify the password
        is_valid = self.verify(password, hashed_password)

        if not is_valid:
            return False, None

        # Check if rehashing is needed
        new_hash = None
        if self.check_needs_rehash(hashed_password):
            try:
                new_hash = self.hash(password)
                logger.info(
                    f"Password needs rehashing, new hash generated on level {self.level}",
                )
            except Exception as e:
                logger.exception("Error generating new hash")
                mssg = "Failed to rehash password"
                raise PasswordRehashError(mssg) from e

        return is_valid, new_hash

    def get_hash_info(self, hashed_password: str) -> dict:
        """
        Extract and return information about a hashed password.

        Args:
            hashed_password: The hashed password to analyze

        Returns:
            dict: Information about the hash including:
                - scheme: The hashing algorithm used
                - deprecated: Whether the scheme is deprecated
                - needs_update: Whether the hash needs updating

        Example:
            >>> hasher = PasswordHasher()
            >>> hashed = hasher.hash("password")
            >>> info = hasher.get_hash_info(hashed)
            >>> print(info)
            {'scheme': 'argon2', 'deprecated': False, 'needs_update': False}
        """
        try:
            scheme = self.pwd_context.identify(hashed_password)
            needs_update = self.check_needs_rehash(hashed_password)

            info = {
                "scheme": scheme,
                "deprecated": scheme != "argon2",
                "needs_update": needs_update,
            }
        except Exception as e:
            logger.exception(f"Error extracting hash info on level {self.level}")
            return {"error": str(e)}
        return info


_default_hasher = PasswordHasher()


def get_password_hasher() -> PasswordHasher:
    """
    Get or create the default password hasher instance.

    Returns:
        PasswordHasher: The singleton password hasher instance

    Example:
        >>> hasher = get_password_hasher()
        >>> hashed = hasher.hash("password")
    """
    return _default_hasher


@with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
async def hash_password(password: str) -> str:
    """
    Module-level function to hash a password using the default hasher.

    Args:
        password: The plaintext password to hash

    Returns:
        str: The hashed password

    Example:
        >>> hashed = hash_password("my_password")
    """

    hashed = await get_event_loop().run_in_executor(
        executor,
        get_password_hasher().hash,
        password,
    )
    return hashed


@with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
async def verify_password(password: str, hashed_password: str) -> bool:
    """
    Module-level function to verify a password using the default hasher.

    Args:
        password: The plaintext password to verify
        hashed_password: The hashed password to verify against

    Returns:
        bool: True if password matches, False otherwise

    Example:
        >>> is_valid = verify_password("my_password", hashed_password)
    """
    return await get_event_loop().run_in_executor(
        executor,
        get_password_hasher().verify,
        password,
        hashed_password,
    )


@with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
async def verify_and_update_password(
    password: str,
    hashed_password: str | None,
) -> tuple[bool, str | None]:
    """
    Module-level function to verify a password and get a new hash if needed.

    Args:
        password: The plaintext password to verify
        hashed_password: The hashed password (can be None)

    Returns:
        tuple[bool, str | None]: Verification result and new hash if needed

    Example:
        >>> is_valid, new_hash = verify_and_update_password("password", hashed)
    """
    return await get_event_loop().run_in_executor(
        executor,
        get_password_hasher().verify_and_update,
        password,
        hashed_password,
    )


@with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
async def password_info(hashed_password: str) -> dict:
    """
    Module-level function to get information about a hashed password.

    Args:
        hashed_password: The hashed password to analyze

    Returns:
        dict: Information about the hash

    Example:
        >>> info = password_info(hashed_password)
    """
    return await get_event_loop().run_in_executor(
        executor,
        get_password_hasher().get_hash_info,
        hashed_password,
    )
