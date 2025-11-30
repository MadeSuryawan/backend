"""Cache statistics and monitoring module."""

from dataclasses import dataclass, field
from logging import getLogger
from threading import Lock

from app.configs import file_logger
from app.utils import today_str

logger = file_logger(getLogger(__name__))


@dataclass
class CacheStatistics:
    """Cache statistics tracker."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    errors: int = 0
    total_bytes_written: int = 0
    total_bytes_read: int = 0
    created_at: str = field(default_factory=today_str)
    last_updated_at: str = field(default_factory=today_str)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def record_hit(self) -> None:
        """Record cache hit."""
        with self._lock:
            self.hits += 1
            self.last_updated_at = today_str()

    def record_miss(self) -> None:
        """Record cache miss."""
        with self._lock:
            self.misses += 1
            self.last_updated_at = today_str()

    def record_set(self, bytes_written: int = 0) -> None:
        """
        Record cache set operation.

        Args:
            bytes_written: Number of bytes written.
        """
        with self._lock:
            self.sets += 1
            self.total_bytes_written += bytes_written
            self.last_updated_at = today_str()

    def record_delete(self) -> None:
        """Record cache delete operation."""
        with self._lock:
            self.deletes += 1
            self.last_updated_at = today_str()

    def record_eviction(self) -> None:
        """Record cache eviction."""
        with self._lock:
            self.evictions += 1
            self.last_updated_at = today_str()

    def record_error(self) -> None:
        """Record cache error."""
        with self._lock:
            self.errors += 1
            self.last_updated_at = today_str()

    def record_read(self, bytes_read: int = 0) -> None:
        """
        Record bytes read from cache.

        Args:
            bytes_read: Number of bytes read.
        """
        with self._lock:
            self.total_bytes_read += bytes_read
            self.last_updated_at = today_str()

    @property
    def hit_rate(self) -> float:
        """
        Calculate cache hit rate.

        Returns:
            Hit rate as percentage (0-100).
        """
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def total_requests(self) -> int:
        """
        Get total requests.

        Returns:
            Total cache requests.
        """
        return self.hits + self.misses

    def reset(self) -> None:
        """Reset statistics."""
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.sets = 0
            self.deletes = 0
            self.evictions = 0
            self.errors = 0
            self.total_bytes_written = 0
            self.total_bytes_read = 0
            self.created_at = today_str()
            self.last_updated_at = today_str()

    def to_dict(self) -> dict[str, int | float | str]:
        """
        Convert statistics to dictionary.

        Returns:
            Dictionary representation of statistics.
        """
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "sets": self.sets,
                "deletes": self.deletes,
                "evictions": self.evictions,
                "errors": self.errors,
                "total_bytes_written": self.total_bytes_written,
                "total_bytes_read": self.total_bytes_read,
                "hit_rate": f"{self.hit_rate:.2f}%",
                "total_requests": self.total_requests,
                "created_at": self.created_at,
                "last_updated_at": self.last_updated_at,
            }
