"""Review repository for database operations."""

from datetime import UTC, datetime
from logging import getLogger
from typing import Any, cast
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnElement

from app.models.review import ReviewDB
from app.repositories.base import BaseRepository
from app.schemas.review import ReviewCreate, ReviewUpdate
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class ReviewRepository(BaseRepository[ReviewDB, ReviewCreate, ReviewUpdate]):
    """
    Repository for Review database operations.

    This class implements the repository pattern for Review entities,
    providing CRUD operations and business logic.
    """

    model = ReviewDB

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with a database session."""
        super().__init__(session)

    async def create(
        self,
        schema: ReviewCreate,
        user_id: UUID | None = None,
        **kwargs: dict[str, Any],
    ) -> ReviewDB:
        """
        Create a new review.

        Args:
            schema: Review creation data
            user_id: ID of the user creating the review
            **kwargs: Additional arguments for creation

        Returns:
            ReviewDB: Created review
        """
        if user_id is None:
            detail = "user_id is required for creating a review"
            raise ValueError(detail)

        db_review = ReviewDB(
            user_id=user_id,
            item_id=schema.item_id,
            rating=schema.rating,
            title=schema.title,
            content=schema.content,
            images_url=None,
            is_verified_purchase=False,
            helpful_count=0,
            created_at=datetime.now(tz=UTC).replace(second=0, microsecond=0),
            updated_at=None,
        )

        return await self._add_and_refresh(db_review)

    async def get_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> list[ReviewDB]:
        """
        Get reviews by user ID.

        Args:
            user_id: User ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[ReviewDB]: List of reviews
        """
        stmt = (
            select(ReviewDB)
            .where(cast(ColumnElement[bool], ReviewDB.user_id == user_id))
            .order_by(desc(cast(ColumnElement[Any], ReviewDB.created_at)))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_item(
        self,
        item_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> list[ReviewDB]:
        """
        Get reviews by item ID.

        Args:
            item_id: Item ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[ReviewDB]: List of reviews
        """
        stmt = (
            select(ReviewDB)
            .where(cast(ColumnElement[bool], ReviewDB.item_id == item_id))
            .order_by(desc(cast(ColumnElement[Any], ReviewDB.created_at)))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        record_id: UUID,
        schema: ReviewUpdate,
    ) -> ReviewDB | None:
        """
        Update a review.

        Args:
            record_id: Review ID
            schema: Update data

        Returns:
            ReviewDB | None: Updated review or None if not found
        """
        db_review = await self.get_by_id(record_id)
        if not db_review:
            return None

        update_data = schema.model_dump(exclude_unset=True, exclude_none=True)
        update_data["updated_at"] = datetime.now(tz=UTC).replace(second=0, microsecond=0)

        for key, value in update_data.items():
            setattr(db_review, key, value)

        await self.session.commit()
        await self.session.refresh(db_review)
        return db_review

    async def remove_image_by_media_id(self, review_id: UUID, media_id: str) -> bool:
        """Remove an image URL from a review by media_id."""
        db_review = await self.get_by_id(review_id)
        if not db_review:
            return False

        if not db_review.images_url:
            return False

        original = list(db_review.images_url)
        updated = [url for url in original if media_id not in url]

        if len(updated) == len(original):
            return False

        db_review.images_url = updated or None
        db_review.updated_at = datetime.now(tz=UTC).replace(second=0, microsecond=0)

        await self.session.commit()
        await self.session.refresh(db_review)
        return True

    async def add_image(self, review_id: UUID, image_url: str) -> ReviewDB | None:
        """Add an image URL to a review."""
        db_review = await self.get_by_id(review_id)
        if not db_review:
            return None

        images = db_review.images_url or []
        images.append(image_url)
        db_review.images_url = images
        db_review.updated_at = datetime.now(tz=UTC).replace(second=0, microsecond=0)

        await self.session.commit()
        await self.session.refresh(db_review)
        return db_review
