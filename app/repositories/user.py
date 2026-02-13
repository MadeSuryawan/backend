"""User repository for database operations."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.managers.password_manager import hash_password, verify_password
from app.models.user import UserDB
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate, UserUpdate


def compute_display_name(first_name: str | None, last_name: str | None, username: str) -> str:
    """
    Compute display name from first name, last name, or fallback to username.

    Args:
        first_name: User's first name.
        last_name: User's last name.
        username: User's username (fallback).

    Returns:
        Display name string.
    """
    if first_name and last_name:
        return f"{first_name} {last_name}"
    return username


class UserRepository(BaseRepository[UserDB, UserCreate, UserUpdate]):
    """
    Repository for User database operations.

    This class implements the repository pattern for User entities,
    providing CRUD operations and business logic.
    """

    model = UserDB
    id_field = "uuid"

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: Async database session
        """
        super().__init__(session)

    async def create(
        self,
        schema: UserCreate,
        timezone: str | None = None,
        auth_provider: str = "email",
        provider_id: str | None = None,
        *,
        is_verified: bool = False,
        **kwargs: dict[str, Any],
    ) -> UserDB:
        """
        Create a new user in the database.

        Args:
            schema: User schema with user data
            timezone: IANA timezone string (e.g., 'Asia/Makassar')
            auth_provider: Authentication provider ('email', 'google', 'wechat')
            provider_id: External provider user ID
            is_verified: Whether the user's email is pre-verified (e.g., OAuth)
            **kwargs: Additional arguments for creation

        Returns:
            UserDB: Created user database model

        Raises:
            DuplicateEntryError: If username or email already exists
            DatabaseError: For other database errors
        """
        password_hash = None
        if schema.password:
            password_hash = await hash_password(schema.password.get_secret_value())

        db_user = UserDB(
            username=schema.username,
            email=schema.email,
            password_hash=password_hash,
            first_name=schema.first_name,
            last_name=schema.last_name,
            display_name=compute_display_name(schema.first_name, schema.last_name, schema.username),
            bio=schema.bio,
            profile_picture=str(schema.profile_picture) if schema.profile_picture else None,
            website=str(schema.website) if schema.website else None,
            date_of_birth=schema.date_of_birth,
            gender=schema.gender,
            phone_number=schema.phone_number,
            country=schema.country,
            timezone=timezone,
            auth_provider=auth_provider,
            provider_id=provider_id,
            is_verified=is_verified,
        )

        # Use the base class helper method for consistent error handling
        return await self._add_and_refresh(db_user)

    async def get_by_username(self, username: str) -> UserDB | None:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            UserDB | None: User if found, None otherwise
        """
        return await self.get_by_field("username", username)

    async def get_by_email(self, email: str) -> UserDB | None:
        """
        Get user by email.

        Args:
            email: Email to search for

        Returns:
            UserDB | None: User if found, None otherwise
        """
        return await self.get_by_field("email", email)

    async def update(self, record_id: UUID, schema: UserUpdate | dict[str, Any]) -> UserDB | None:
        """
        Update user information.

        Args:
            record_id: User UUID
            schema: User update schema or dict with fields to update

        Returns:
            UserDB | None: Updated user if found, None otherwise

        Raises:
            DuplicateEntryError: If email already exists for another user
            DatabaseError: For other database errors
        """
        db_user = await self.get_by_id(record_id)
        if not db_user:
            return None

        if isinstance(schema, dict):
            update_data = schema
        else:
            update_data = schema.model_dump(exclude_unset=True, exclude_none=True)

        if not isinstance(schema, dict) and schema.password:
            password_hash = await hash_password(schema.password.get_secret_value())
            update_data["password_hash"] = password_hash
            update_data.pop("password", None)
            update_data.pop("confirmed_password", None)

        if "profile_picture" in update_data and update_data["profile_picture"]:
            update_data["profile_picture"] = str(update_data["profile_picture"])
        if "website" in update_data and update_data["website"]:
            update_data["website"] = str(update_data["website"])

        # Recompute display_name if first_name or last_name is being updated
        if "first_name" in update_data or "last_name" in update_data:
            new_first_name = update_data.get("first_name", db_user.first_name)
            new_last_name = update_data.get("last_name", db_user.last_name)
            update_data["display_name"] = compute_display_name(
                new_first_name,
                new_last_name,
                db_user.username,
            )

        update_data["updated_at"] = datetime.now(tz=UTC).replace(second=0, microsecond=0)

        for key, value in update_data.items():
            setattr(db_user, key, value)

        return await self._add_and_refresh(db_user)

    async def do_password_verify(self, username: str, password: str) -> UserDB | None:
        """
        Verify user credentials.

        Args:
            username: Username
            password: Plain text password

        Returns:
            UserDB | None: User if credentials are valid, None otherwise
        """
        db_user = await self.get_by_username(username)
        if not db_user:
            return None

        if not db_user.password_hash:
            return None

        if not await verify_password(password, db_user.password_hash):
            return None

        return db_user
