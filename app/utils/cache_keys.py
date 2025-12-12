"""
Cache key builders for the application.

This module contains functions to generate consistent cache keys for various
entities in the system, ensuring that different parts of the application
(e.g. routes, services) can coordinate cache invalidation.
"""

from uuid import UUID


def user_id_key(user_id: UUID) -> str:
    """Generate cache key for user by ID."""
    return f"user_by_id_{user_id}"


def username_key(username: str) -> str:
    """Generate cache key for user by username."""
    return f"user_by_username_{username}"


def users_list_key(skip: int, limit: int) -> str:
    """Generate cache key for users list."""
    return f"users_all_{skip}_{limit}"
