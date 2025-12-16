"""Idempotency manager for handling request deduplication."""

from datetime import UTC, datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.clients.protocols import CacheClientProtocol
from app.errors.idempotency import DuplicateRequestError, IdempotencyStorageError
from app.schemas.idempotency import IdempotencyMetrics, IdempotencyRecord, IdempotencyStatus
from app.utils.helpers import file_logger

if TYPE_CHECKING:
    from app.managers.metrics import MetricsManager

logger = file_logger(getLogger(__name__))

# Default TTL: 1 hour (reasonable for API idempotency)
DEFAULT_TTL = 3600


class IdempotencyManager:
    """
    Manager for idempotency operations using Redis backend.

    This class handles the core idempotency logic:
    - Checking if a request has been processed
    - Storing processing/completed/failed states
    - Returning cached responses for duplicate requests
    - Tracking metrics for idempotency operations

    Attributes:
        _cache: Cache client implementing CacheClientProtocol
        _prefix: Key prefix for idempotency records
        _ttl: Time-to-live in seconds for idempotency records
        _metrics: Internal metrics tracking
        _metrics_manager: Optional external metrics manager
    """

    __slots__ = ("_cache", "_metrics", "_metrics_manager", "_prefix", "_ttl")

    def __init__(
        self,
        cache_client: CacheClientProtocol,
        prefix: str = "idempotency",
        ttl: int = DEFAULT_TTL,
        metrics_manager: "MetricsManager | None" = None,
    ) -> None:
        """
        Initialize idempotency manager.

        Args:
            cache_client: Redis client implementing CacheClientProtocol
            prefix: Key prefix for idempotency records
            ttl: Time-to-live in seconds (default: 1 hour)
            metrics_manager: Optional metrics manager for external monitoring
        """
        self._cache = cache_client
        self._prefix = prefix
        self._ttl = ttl
        self._metrics = IdempotencyMetrics()
        self._metrics_manager = metrics_manager

    def _build_key(self, namespace: str, idempotency_key: str) -> str:
        """
        Build Redis key for idempotency record.

        Args:
            namespace: Operation namespace (e.g., 'auth:register')
            idempotency_key: Unique request identifier

        Returns:
            Full Redis key string
        """
        return f"{self._prefix}:{namespace}:{idempotency_key}"

    async def check_and_set_processing(
        self,
        namespace: str,
        idempotency_key: str | UUID,
    ) -> IdempotencyRecord | None:
        """
        Check if request exists and set to processing if not.

        This method implements atomic check-and-set logic:
        1. If key exists and status is PROCESSING -> raises DuplicateRequestError
        2. If key exists and status is COMPLETED -> returns cached record
        3. If key exists and status is FAILED -> allows retry (returns None)
        4. If key doesn't exist -> sets PROCESSING and returns None

        Args:
            namespace: Operation namespace (e.g., 'auth:register')
            idempotency_key: Unique request identifier

        Returns:
            Existing IdempotencyRecord if found and completed, None if new request or failed

        Raises:
            DuplicateRequestError: If request is currently processing
            IdempotencyStorageError: If storage operation fails
        """
        key = self._build_key(namespace, str(idempotency_key))
        self._metrics.total_requests += 1

        try:
            # Try to get existing record
            existing = await self._cache.get(key)
            if existing:
                record = IdempotencyRecord.model_validate_json(existing)

                if record.status == IdempotencyStatus.PROCESSING:
                    # Request is still being processed - block duplicate
                    self._metrics.duplicate_requests_blocked += 1
                    logger.warning(
                        f"Duplicate request blocked for idempotency key: {idempotency_key}",
                    )
                    raise DuplicateRequestError(str(idempotency_key))

                if record.status == IdempotencyStatus.COMPLETED:
                    # Return completed response (cache hit)
                    self._metrics.cache_hits += 1
                    logger.info(
                        f"Returning cached response for idempotency key: {idempotency_key}",
                    )
                    return record

                # FAILED status - allow retry (return None to proceed)
                logger.info(
                    f"Previous request failed, allowing retry for key: {idempotency_key}",
                )
                self._metrics.cache_misses += 1

            else:
                self._metrics.cache_misses += 1

            # Set new processing record
            new_record = IdempotencyRecord(status=IdempotencyStatus.PROCESSING)
            await self._cache.set(
                key,
                new_record.model_dump_json(),
                ex=self._ttl,
            )
            logger.debug(f"Set processing status for idempotency key: {idempotency_key}")
            return None

        except DuplicateRequestError:
            raise
        except Exception as e:
            logger.exception(f"Idempotency storage error: {e}")
            raise IdempotencyStorageError("check_and_set", str(e)) from e

    async def set_completed(
        self,
        namespace: str,
        idempotency_key: str | UUID,
        response: Any,
    ) -> None:
        """
        Mark request as completed with response.

        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier
            response: Response to cache (will be serialized to JSON)

        Raises:
            IdempotencyStorageError: If storage operation fails
        """
        key = self._build_key(namespace, str(idempotency_key))
        try:
            record = IdempotencyRecord(
                status=IdempotencyStatus.COMPLETED,
                response=response,
                completed_at=datetime.now(UTC),
            )
            await self._cache.set(
                key,
                record.model_dump_json(),
                ex=self._ttl,
            )
            logger.debug(f"Set completed status for idempotency key: {idempotency_key}")
        except Exception as e:
            logger.exception(f"Failed to set completed status: {e}")
            raise IdempotencyStorageError("set_completed", str(e)) from e

    async def set_failed(
        self,
        namespace: str,
        idempotency_key: str | UUID,
        error: str,
    ) -> None:
        """
        Mark request as failed with error.

        Failed records allow retry - the next request with the same key
        will be processed again.

        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier
            error: Error message to store

        Raises:
            IdempotencyStorageError: If storage operation fails
        """
        key = self._build_key(namespace, str(idempotency_key))
        self._metrics.failed_requests += 1

        try:
            record = IdempotencyRecord(
                status=IdempotencyStatus.FAILED,
                error=error,
                completed_at=datetime.now(UTC),
            )
            await self._cache.set(
                key,
                record.model_dump_json(),
                ex=self._ttl,
            )
            logger.debug(f"Set failed status for idempotency key: {idempotency_key}")
        except Exception as e:
            logger.exception(f"Failed to set failed status: {e}")
            raise IdempotencyStorageError("set_failed", str(e)) from e

    async def get_record(
        self,
        namespace: str,
        idempotency_key: str | UUID,
    ) -> IdempotencyRecord | None:
        """
        Get idempotency record without modifying it.

        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier

        Returns:
            IdempotencyRecord if found, None otherwise

        Raises:
            IdempotencyStorageError: If storage operation fails
        """
        key = self._build_key(namespace, str(idempotency_key))
        try:
            existing = await self._cache.get(key)
            if existing:
                return IdempotencyRecord.model_validate_json(existing)
            return None
        except Exception as e:
            logger.exception(f"Failed to get idempotency record: {e}")
            raise IdempotencyStorageError("get_record", str(e)) from e

    async def delete(
        self,
        namespace: str,
        idempotency_key: str | UUID,
    ) -> bool:
        """
        Delete idempotency record (for admin/testing purposes).

        Args:
            namespace: Operation namespace
            idempotency_key: Unique request identifier

        Returns:
            True if deleted, False if not found

        Raises:
            IdempotencyStorageError: If storage operation fails
        """
        key = self._build_key(namespace, str(idempotency_key))
        try:
            result = await self._cache.delete(key)
            deleted = result > 0
            if deleted:
                logger.info(f"Deleted idempotency record for key: {idempotency_key}")
            return deleted
        except Exception as e:
            logger.exception(f"Failed to delete idempotency record: {e}")
            raise IdempotencyStorageError("delete", str(e)) from e

    async def clear_namespace(self, namespace: str) -> int:
        """
        Clear all idempotency records for a namespace (admin operation).

        Note: This operation scans keys, which may be slow for large datasets.

        Args:
            namespace: Operation namespace to clear

        Returns:
            Number of records deleted

        Raises:
            IdempotencyStorageError: If operation fails
        """
        pattern = f"{self._prefix}:{namespace}:*"
        deleted_count = 0

        try:
            # Check if cache client has scan_iter method (RedisClient)
            if hasattr(self._cache, "scan_iter"):
                keys_to_delete: list[str] = []
                async for key in self._cache.scan_iter(pattern):
                    keys_to_delete.append(key)

                if keys_to_delete:
                    deleted_count = await self._cache.delete(*keys_to_delete)
                    logger.info(
                        f"Cleared {deleted_count} idempotency records for namespace: {namespace}",
                    )
            else:
                logger.warning(
                    f"Cache client doesn't support scan_iter, cannot clear namespace: {namespace}",
                )

            return deleted_count
        except Exception as e:
            logger.exception(f"Failed to clear namespace: {e}")
            raise IdempotencyStorageError("clear_namespace", str(e)) from e

    def get_metrics(self) -> IdempotencyMetrics:
        """
        Get current idempotency metrics.

        Returns:
            IdempotencyMetrics with current statistics
        """
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset all idempotency metrics to zero."""
        self._metrics = IdempotencyMetrics()
        logger.info("Idempotency metrics reset")

    def set_metrics_manager(self, metrics_manager: "MetricsManager") -> None:
        """
        Set external metrics manager for monitoring.

        Args:
            metrics_manager: MetricsManager instance
        """
        self._metrics_manager = metrics_manager

    @property
    def ttl(self) -> int:
        """Get current TTL setting."""
        return self._ttl

    @property
    def prefix(self) -> str:
        """Get current key prefix."""
        return self._prefix

    # =========================================================================
    # Admin operations (work with raw keys)
    # =========================================================================

    async def get_record_by_key(self, key: str) -> IdempotencyRecord | None:
        """
        Get idempotency record by raw key (admin operation).

        Args:
            key: Full idempotency key or just the UUID part

        Returns:
            IdempotencyRecord if found, None otherwise
        """
        try:
            # First try with exact key
            existing = await self._cache.get(key)
            if existing:
                return IdempotencyRecord.model_validate_json(existing)

            # If not found, try searching for keys containing this value
            if hasattr(self._cache, "scan_iter"):
                pattern = f"{self._prefix}:*:{key}"
                async for full_key in self._cache.scan_iter(pattern):
                    existing = await self._cache.get(full_key)
                    if existing:
                        return IdempotencyRecord.model_validate_json(existing)

            return None
        except Exception as e:
            logger.exception(f"Failed to get record by key: {e}")
            raise IdempotencyStorageError("get_record_by_key", str(e)) from e

    async def delete_key(self, key: str) -> bool:
        """
        Delete idempotency record by raw key (admin operation).

        Args:
            key: Full idempotency key or just the UUID part

        Returns:
            True if deleted, False if not found
        """
        try:
            # First try with exact key
            result = await self._cache.delete(key)
            if result > 0:
                logger.info(f"Deleted idempotency record for key: {key}")
                return True

            # If not found, try searching for keys containing this value
            if hasattr(self._cache, "scan_iter"):
                pattern = f"{self._prefix}:*:{key}"
                async for full_key in self._cache.scan_iter(pattern):
                    result = await self._cache.delete(full_key)
                    if result > 0:
                        logger.info(f"Deleted idempotency record for key: {full_key}")
                        return True

            return False
        except Exception as e:
            logger.exception(f"Failed to delete key: {e}")
            raise IdempotencyStorageError("delete_key", str(e)) from e

    async def clear_all(self) -> int:
        """
        Clear all idempotency records (admin operation).

        Returns:
            Number of records deleted

        Raises:
            IdempotencyStorageError: If operation fails
        """
        pattern = f"{self._prefix}:*"
        deleted_count = 0

        try:
            if hasattr(self._cache, "scan_iter"):
                keys_to_delete: list[str] = []
                async for key in self._cache.scan_iter(pattern):
                    keys_to_delete.append(key)

                if keys_to_delete:
                    deleted_count = await self._cache.delete(*keys_to_delete)
                    logger.info(f"Cleared {deleted_count} idempotency records (all namespaces)")

            return deleted_count
        except Exception as e:
            logger.exception(f"Failed to clear all records: {e}")
            raise IdempotencyStorageError("clear_all", str(e)) from e
