"""User repository for database operations."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnElement

from app.errors.database import DatabaseError, DuplicateEntryError
from app.managers import hash_password, verify_password
from app.models.user import UserDB
from app.schemas.user import UserCreate, UserUpdate


class UserRepository:
    """
    Repository for User database operations.

    This class implements the repository pattern for User entities,
    providing CRUD operations and business logic.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def create(self, user: UserCreate) -> UserDB:
        """
        Create a new user in the database.

        Args:
            user: User schema with user data

        Returns:
            UserDB: Created user database model

        Raises:
            DuplicateEntryError: If username or email already exists
            DatabaseError: For other database errors
        """
        password_hash = hash_password(user.password.get_secret_value())

        db_user = UserDB(
            username=user.username,
            email=user.email,
            password_hash=password_hash,
            first_name=user.first_name,
            last_name=user.last_name,
            bio=user.bio,
            profile_picture=str(user.profile_picture) if user.profile_picture else None,
            website=str(user.website) if user.website else None,
            date_of_birth=user.date_of_birth,
            gender=user.gender,
            phone_number=user.phone_number,
            country=user.country,
        )

        try:
            self.session.add(db_user)
            await self.session.flush()
            await self.session.refresh(db_user)
            return db_user
        except IntegrityError as e:
            await self.session.rollback()
            error_msg = str(e.orig) if e.orig else str(e)
            if "username" in error_msg.lower():
                raise DuplicateEntryError(
                    detail=f"Username '{user.username}' already exists",
                ) from e
            if "email" in error_msg.lower():
                raise DuplicateEntryError(
                    detail=f"Email '{user.email}' already exists",
                ) from e
            raise DatabaseError(detail=f"Database integrity error: {error_msg}") from e

    async def get_by_id(self, user_id: UUID) -> UserDB | None:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            UserDB | None: User if found, None otherwise
        """
        result = await self.session.execute(
            select(UserDB).where(cast(ColumnElement[bool], UserDB.uuid == user_id)),
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> UserDB | None:
        """
        Get user by username.

        Args:
            username: Username to search for

        Returns:
            UserDB | None: User if found, None otherwise
        """
        result = await self.session.execute(
            select(UserDB).where(cast(ColumnElement[bool], UserDB.username == username)),
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserDB | None:
        """
        Get user by email.

        Args:
            email: Email to search for

        Returns:
            UserDB | None: User if found, None otherwise
        """
        result = await self.session.execute(
            select(UserDB).where(cast(ColumnElement[bool], UserDB.email == email)),
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> list[UserDB]:
        """
        Get all users with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[UserDB]: List of users
        """
        result = await self.session.execute(
            select(UserDB).offset(skip).limit(limit),
        )
        return list(result.scalars().all())

    async def update(self, user_id: UUID, user_update: UserUpdate) -> UserDB | None:
        """
        Update user information.

        Args:
            user_id: User UUID
            user_update: User update schema with fields to update

        Returns:
            UserDB | None: Updated user if found, None otherwise

        Raises:
            DuplicateEntryError: If email already exists for another user
            DatabaseError: For other database errors
        """
        db_user = await self.get_by_id(user_id)
        if not db_user:
            return None

        update_data = user_update.model_dump(exclude_unset=True, exclude_none=True)

        if user_update.password:
            password_hash = hash_password(user_update.password.get_secret_value())
            update_data["password_hash"] = password_hash
            update_data.pop("password", None)
            update_data.pop("confirmed_password", None)

        if "profile_picture" in update_data and update_data["profile_picture"]:
            update_data["profile_picture"] = str(update_data["profile_picture"])
        if "website" in update_data and update_data["website"]:
            update_data["website"] = str(update_data["website"])

        update_data["updated_at"] = datetime.now(tz=UTC)

        for key, value in update_data.items():
            setattr(db_user, key, value)

        try:
            await self.session.flush()
            await self.session.refresh(db_user)
            return db_user
        except IntegrityError as e:
            await self.session.rollback()
            error_msg = str(e.orig) if e.orig else str(e)
            if "email" in error_msg.lower():
                raise DuplicateEntryError(
                    detail=f"Email '{user_update.email}' already exists",
                ) from e
            raise DatabaseError(detail=f"Database integrity error: {error_msg}") from e

    async def delete(self, user_id: UUID) -> bool:
        """
        Delete user by ID.

        Args:
            user_id: User UUID

        Returns:
            bool: True if user was deleted, False if not found
        """
        db_user = await self.get_by_id(user_id)
        if not db_user:
            return False

        await self.session.delete(db_user)
        await self.session.flush()

        return True

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

        if not verify_password(password, db_user.password_hash):
            return None

        return db_user
