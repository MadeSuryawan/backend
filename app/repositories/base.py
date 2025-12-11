"""Base repository for database operations."""

from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.errors.database import (
    DatabaseConnectionError,
    DatabaseError,
    DuplicateEntryError,
    RecordNotFoundError,
)


class BaseRepository[ModelT: SQLModel, CreateSchemaT, UpdateSchemaT](ABC):
    """
    Abstract base repository implementing common CRUD operations.

    This class provides a generic implementation of database operations
    that can be extended by specific entity repositories.

    Type Parameters:
        ModelT: The SQLModel database model type
        CreateSchemaT: The Pydantic schema for creation
        UpdateSchemaT: The Pydantic schema for updates
    """

    model: type[ModelT]
    id_field: str = "id"

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    @abstractmethod
    async def create(self, schema: CreateSchemaT) -> ModelT:
        """
        Create a new record in the database.

        Args:
            schema: Creation schema with data

        Returns:
            ModelT: Created database model
        """
        ...

    async def get_by_id(self, record_id: UUID) -> ModelT | None:
        """
        Get a record by its ID.

        Args:
            record_id: Record UUID

        Returns:
            ModelT | None: Record if found, None otherwise
        """
        id_column = getattr(self.model, self.id_field)
        result = await self.session.execute(
            select(self.model).where(id_column == record_id),
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 10,
    ) -> list[ModelT]:
        """
        Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[ModelT]: List of records
        """
        result = await self.session.execute(
            select(self.model).offset(skip).limit(limit),
        )
        return list(result.scalars().all())

    @abstractmethod
    async def update(
        self,
        record_id: UUID,
        schema: UpdateSchemaT,
    ) -> ModelT | None:
        """
        Update a record.

        Args:
            record_id: Record UUID
            schema: Update schema with fields to update

        Returns:
            ModelT | None: Updated record if found, None otherwise
        """
        ...

    async def delete(self, record_id: UUID) -> bool:
        """
        Delete a record by ID.

        Args:
            record_id: Record UUID

        Returns:
            bool: True if record was deleted, False if not found
        """
        record = await self.get_by_id(record_id)
        if not record:
            return False

        await self.session.delete(record)
        await self.session.flush()

        return True

    async def exists(self, record_id: UUID) -> bool:
        """
        Check if a record exists.

        Args:
            record_id: Record UUID

        Returns:
            bool: True if record exists, False otherwise
        """
        record = await self.get_by_id(record_id)
        return record is not None

    async def count(self) -> int:
        """
        Count total records.

        Returns:
            int: Total number of records
        """
        result = await self.session.execute(
            select(func.count()).select_from(self.model),
        )
        count = result.scalar()
        return count if count is not None else 0

    async def _add_and_refresh(self, record: ModelT) -> ModelT:
        """
        Add a record and refresh it from the database.

        Args:
            record: Record to add

        Returns:
            ModelT: Refreshed record

        Raises:
            DuplicateEntryError: If a unique constraint is violated
            DatabaseError: For other database errors
        """
        try:
            self.session.add(record)
            await self.session.flush()
            await self.session.refresh(record)
            return record
        except IntegrityError as e:
            await self.session.rollback()
            error_msg = str(e.orig) if e.orig else str(e)
            if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
                raise DuplicateEntryError(detail=error_msg) from e
            raise DatabaseError(detail=f"Database integrity error: {error_msg}") from e
        except Exception as e:
            await self.session.rollback()
            raise DatabaseConnectionError(
                detail=f"Failed to save record: {e}",
            ) from e

    async def _check_exists_by_field(
        self,
        field_name: str,
        value: str | UUID,
        exclude_id: UUID | None = None,
    ) -> bool:
        """
        Check if a record exists with a specific field value.

        Args:
            field_name: Name of the field to check
            value: Value to check for
            exclude_id: Optional ID to exclude from check (for updates)

        Returns:
            bool: True if record exists, False otherwise
        """
        field = getattr(self.model, field_name)
        query = select(self.model).where(field == value)

        if exclude_id is not None:
            id_column = getattr(self.model, self.id_field)
            query = query.where(id_column != exclude_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_by_field(
        self,
        field_name: str,
        value: str | UUID,
    ) -> ModelT | None:
        """
        Get a record by a specific field value.

        Args:
            field_name: Name of the field to search
            value: Value to search for

        Returns:
            ModelT | None: Record if found, None otherwise
        """
        field = getattr(self.model, field_name)
        result = await self.session.execute(
            select(self.model).where(field == value),
        )
        return result.scalar_one_or_none()

    async def get_or_raise(self, record_id: UUID) -> ModelT:
        """
        Get a record by ID or raise an exception if not found.

        Args:
            record_id: Record UUID

        Returns:
            ModelT: Record if found

        Raises:
            RecordNotFoundError: If record is not found
        """
        record = await self.get_by_id(record_id)
        if not record:
            raise RecordNotFoundError(
                detail=f"{self.model.__name__} with ID {record_id} not found",
            )
        return record
