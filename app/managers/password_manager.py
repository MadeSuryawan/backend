"""
Password hashing module using Argon2id with direct argon2-cffi.

This module provides secure password hashing and verification using Argon2id,
which is considered one of the most secure password hashing algorithms available.

Migration from passlib to argon2-cffi - simplified version (no legacy support).
Uses current security levels to maintain existing protection.
"""

from asyncio import get_event_loop
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from typing import ClassVar

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from app.configs.argon2 import Argon2Config, get_argon2_config
from app.configs.settings import settings
from app.decorators.with_retry import with_retry
from app.errors import PasswordHashingError, PasswordRehashError
from app.logging import get_logger

logger = get_logger(__name__)


class Argon2Hasher:
    """
    Direct argon2-cffi implementation for password hashing.

    This class provides secure password hashing using argon2-cffi directly,
    eliminating the passlib dependency.
    """

    CURRENT_VERSION: ClassVar[str] = "v=19"

    def __init__(self, config: Argon2Config | None = None) -> None:
        """Initialize the hasher with specified or default configuration."""
        self.config = config or self._get_config_for_level()
        self._hasher = PasswordHasher(
            time_cost=self.config.time_cost,
            memory_cost=self.config.memory_cost,
            parallelism=self.config.parallelism,
            hash_len=self.config.hash_len,
            type=self.config.type,
        )
        self.level = settings.PASSWORD_SECURITY_LEVEL
        logger.info("Argon2Hasher initialized on level %s", self.level)

    def _get_config_for_level(self) -> Argon2Config:
        """Get configuration based on current security level setting."""
        level = settings.PASSWORD_SECURITY_LEVEL
        return get_argon2_config(level, settings.ENVIRONMENT)

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
        """
        if not password:
            msg = "Password cannot be empty"
            raise ValueError(msg)

        try:
            hashed = self._hasher.hash(password)
            logger.debug("Password hashed successfully")
            return hashed
        except HashingError as e:
            logger.exception("Error hashing password")
            mssg = "Failed to hash password"
            raise PasswordHashingError(mssg) from e

    def verify(self, password: str, hashed_password: str) -> bool:
        """
        Verify a plaintext password against a hashed password.

        Args:
            password: The plaintext password to verify
            hashed_password: The hashed password to verify against

        Returns:
            bool: True if password matches, False otherwise

        Example:
            >>> hasher = Argon2Hasher()
            >>> hashed = hasher.hash("my_password")
            >>> hasher.verify("my_password", hashed)
            True
            >>> hasher.verify("wrong_password", hashed)
            False
        """
        if not hashed_password or not isinstance(hashed_password, str):
            logger.warning("Invalid hash format provided")
            return False

        try:
            self._hasher.verify(hashed_password, password)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False
        except VerificationError:
            logger.warning("Verification failed due to invalid hash")
            return False
        except Exception:
            logger.exception("Unexpected error during verification")
            return False

    def check_needs_rehash(self, hashed_password: str) -> bool:
        """
        Check if a hashed password needs to be rehashed due to outdated parameters.

        Args:
            hashed_password: The hashed password to check

        Returns:
            bool: True if rehashing is needed, False otherwise
        """
        if not hashed_password:
            return True

        try:
            return self._needs_parameters_upgrade(hashed_password)
        except Exception:
            logger.exception("Error checking hash parameters")
            return True

    def _needs_parameters_upgrade(self, hashed_password: str) -> bool:
        """
        Check if hash parameters are below current minimums.

        This parses the existing hash and compares its parameters
        against current configuration requirements.

        Args:
            hashed_password: The hashed password to analyze

        Returns:
            bool: True if parameters need upgrading
        """
        if not hashed_password.startswith("$argon2id$"):
            return True

        try:
            if not self._is_valid_hash_format(hashed_password):
                return True

            if not self._is_current_version(hashed_password):
                return True

            return self._are_parameters_outdated(hashed_password)

        except (ValueError, IndexError):
            return True

    def _is_valid_hash_format(self, hashed_password: str) -> bool:
        """Check if hash has valid format structure."""
        parts = hashed_password.split("$")
        return len(parts) >= 4

    def _is_current_version(self, hashed_password: str) -> bool:
        """Check if hash uses current version."""
        parts = hashed_password.split("$")
        if len(parts) < 3:
            return False
        version = parts[2]
        return version == self.CURRENT_VERSION

    def _are_parameters_outdated(self, hashed_password: str) -> bool:
        """Check if hash parameters are below current minimums."""
        parts = hashed_password.split("$")

        # Validate we have enough parts before accessing
        if len(parts) < 4:
            return True

        params = parts[3]

        current_memory = self.config.memory_cost
        current_time = self.config.time_cost
        current_parallel = self.config.parallelism

        parsed_params = self._parse_hash_parameters(params)

        if parsed_params["memory"] is not None and parsed_params["memory"] < current_memory:
            return True
        if parsed_params["time"] is not None and parsed_params["time"] < current_time:
            return True
        return (
            parsed_params["parallelism"] is not None
            and parsed_params["parallelism"] < current_parallel
        )

    def _parse_hash_parameters(self, params_str: str) -> dict[str, int | None]:
        """Parse hash parameter string into individual values."""
        memory_val: int | None = None
        time_val: int | None = None
        parallel_val: int | None = None

        for param in params_str.split(","):
            if param.startswith("m="):
                memory_val = int(param[2:])
            elif param.startswith("t="):
                time_val = int(param[2:])
            elif param.startswith("p="):
                parallel_val = int(param[2:])

        return {"memory": memory_val, "time": time_val, "parallelism": parallel_val}

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
            tuple[bool, str | None]:
                - First element: True if password is correct, False otherwise
                - Second element: New hash if rehashing needed, None otherwise
        """
        if hashed_password is None:
            logger.warning("Hashed password is None")
            # Perform dummy verification for constant-time behavior.
            # The result is discarded intentionally - this ensures similar computation
            # time regardless of whether a hash is stored in the database.
            # This prevents timing attacks that could enumerate whether a user has
            # a password set (e.g., OAuth-only accounts).
            # Using the same parameters as standard profile to match typical verification time.
            with suppress(Exception):
                self._hasher.verify(settings.PASSWORD_DUMMY_HASH, password)
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
                    "Password needs rehashing, new hash generated",
                )
            except Exception as e:
                logger.exception("Error generating new hash")
                details = "Failed to rehash password"
                raise PasswordRehashError(details) from e

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
        """
        try:
            if not hashed_password.startswith("$argon2id$"):
                return {
                    "scheme": "unknown",
                    "deprecated": True,
                    "needs_update": True,
                }

            parts = hashed_password.split("$")
            version = parts[2] if len(parts) > 2 else "unknown"
            params = parts[3] if len(parts) > 3 else ""

            return {
                "scheme": "argon2id",
                "version": version,
                "deprecated": version != self.CURRENT_VERSION,
                "needs_update": self.check_needs_rehash(hashed_password),
                "parameters": params,
            }
        except Exception as e:
            logger.exception("Error extracting hash info")
            return {"error": str(e)}

    @with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
    async def hash_password(self, password: str) -> str:
        """
        Module-level function to hash a password using the default hasher.

        Args:
            password: The plaintext password to hash

        Returns:
            str: The hashed password

        Example:
            >>> hashed = hash_password("my_password")
        """

        with ThreadPoolExecutor(max_workers=4) as executor:
            return await get_event_loop().run_in_executor(
                executor,
                self.hash,
                password,
            )

    @with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
    async def verify_password(self, password: str, hashed_password: str) -> bool:
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

        with ThreadPoolExecutor(max_workers=4) as executor:
            return await get_event_loop().run_in_executor(
                executor,
                self.verify,
                password,
                hashed_password,
            )

    @with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
    async def verify_and_update_password(
        self,
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
        with ThreadPoolExecutor(max_workers=4) as executor:
            return await get_event_loop().run_in_executor(
                executor,
                self.verify_and_update,
                password,
                hashed_password,
            )

    @with_retry(base_delay=1, max_delay=10, exec_retry=PasswordHashingError)
    async def password_info(self, hashed_password: str) -> dict:
        """
        Module-level function to get information about a hashed password.

        Args:
            hashed_password: The hashed password to analyze

        Returns:
            dict: Information about the hash

        Example:
            >>> info = password_info(hashed_password)
        """
        with ThreadPoolExecutor(max_workers=4) as executor:
            return await get_event_loop().run_in_executor(
                executor,
                self.get_hash_info,
                hashed_password,
            )
