"""Blog repository for database operations."""

from datetime import UTC, datetime
from logging import getLogger
from typing import Literal
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs import file_logger
from app.errors.database import DatabaseError, DuplicateEntryError
from app.models.blog import BlogDB
from app.schemas.blog import Blog, BlogUpdate

logger = file_logger(getLogger(__name__))


def calculate_word_count(content: str) -> int:
    """
    Calculate word count from content.

    Args:
        content: Blog content

    Returns:
        int: Word count
    """
    return len(content.split())


def calculate_reading_time(word_count: int) -> int:
    """
    Calculate reading time in minutes based on word count.

    Assumes average reading speed of 200 words per minute.

    Args:
        word_count: Number of words

    Returns:
        int: Reading time in minutes (minimum 1)
    """
    reading_time = word_count / 200
    return max(1, round(reading_time))


class BlogRepository:
    """
    Repository for Blog database operations.

    This class implements the repository pattern for Blog entities,
    providing CRUD operations and business logic.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def create(self, blog: Blog, author_id: UUID) -> BlogDB:
        """
        Create a new blog post in the database.

        Args:
            blog: Blog schema with blog data
            author_id: UUID of the blog author

        Returns:
            BlogDB: Created blog database model

        Raises:
            DuplicateEntryError: If slug already exists
            DatabaseError: For other database errors
        """
        word_count = calculate_word_count(blog.content)
        reading_time = calculate_reading_time(word_count)

        db_blog = BlogDB(
            author_id=author_id,
            title=blog.title,
            slug=blog.slug,
            content=blog.content,
            summary=blog.summary,
            view_count=0,
            word_count=word_count,
            reading_time_minutes=reading_time,
            status=blog.status if hasattr(blog, "status") and blog.status else "draft",
            tags=blog.tags,
            images_url=[str(url) for url in blog.images_url] if blog.images_url else None,
            created_at=datetime.now(tz=UTC).replace(second=0, microsecond=0),
            updated_at=datetime.now(tz=UTC).replace(second=0, microsecond=0),
        )

        try:
            self.session.add(db_blog)
            await self.session.flush()
            await self.session.refresh(db_blog)
            return db_blog
        except IntegrityError as e:
            await self.session.rollback()
            error_msg = str(e.orig) if e.orig else str(e)
            if "slug" in error_msg.lower():
                raise DuplicateEntryError(
                    detail=f"Blog with slug '{blog.slug}' already exists",
                ) from e
            raise DatabaseError(detail=f"Database integrity error: {error_msg}") from e

    async def get_by_id(self, blog_id: UUID) -> BlogDB | None:
        """
        Get blog by ID.

        Args:
            blog_id: Blog UUID

        Returns:
            BlogDB | None: Blog if found, None otherwise
        """
        result = await self.session.execute(
            # pyrefly: ignore [bad-argument-type]
            select(BlogDB).where(BlogDB.id == blog_id),
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> BlogDB | None:
        """
        Get blog by slug.

        Args:
            slug: Blog slug

        Returns:
            BlogDB | None: Blog if found, None otherwise
        """
        result = await self.session.execute(
            # pyrefly: ignore [bad-argument-type]
            select(BlogDB).where(BlogDB.slug == slug),
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 10,
        status: Literal["draft", "published", "archived"] | None = None,
        author_id: UUID | None = None,
    ) -> list[BlogDB]:
        """
        Get all blogs with pagination and optional filtering.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            status: Optional status filter
            author_id: Optional author ID filter

        Returns:
            list[BlogDB]: List of blogs
        """
        query = select(BlogDB)

        # Apply filters
        if status:
            # pyrefly: ignore [bad-argument-type]
            query = query.where(BlogDB.status == status)
        if author_id:
            # pyrefly: ignore [bad-argument-type]
            query = query.where(BlogDB.author_id == author_id)

        # Apply pagination and ordering
        # pyrefly: ignore [bad-argument-type]
        query = query.order_by(desc(BlogDB.created_at)).offset(skip).limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_author(
        self,
        author_id: UUID,
        skip: int = 0,
        limit: int = 10,
    ) -> list[BlogDB]:
        """
        Get all blogs by a specific author.

        Args:
            author_id: Author UUID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[BlogDB]: List of blogs by the author
        """
        return await self.get_all(skip=skip, limit=limit, author_id=author_id)

    async def update(self, blog_id: UUID, blog_update: BlogUpdate) -> BlogDB | None:
        """
        Update blog information.

        Args:
            blog_id: Blog UUID
            blog_update: Blog update schema with fields to update

        Returns:
            BlogDB | None: Updated blog if found, None otherwise

        Raises:
            ValueError: If slug already exists for another blog
        """
        db_blog = await self.get_by_id(blog_id)
        if not db_blog:
            return None

        # Check if slug is being updated and already exists
        if blog_update.slug:
            existing_blog = await self.get_by_slug(blog_update.slug)
            if existing_blog and existing_blog.id != blog_id:
                msg = f"Slug '{blog_update.slug}' already exists"
                raise ValueError(msg)

        # Update fields
        update_data = blog_update.model_dump(exclude_unset=True, exclude_none=True)

        # Convert image URLs to strings
        if "images_url" in update_data and update_data["images_url"]:
            update_data["images_url"] = [str(url) for url in update_data["images_url"]]

        # Recalculate word count and reading time if content is updated
        if "content" in update_data:
            word_count = calculate_word_count(update_data["content"])
            update_data["word_count"] = word_count
            update_data["reading_time_minutes"] = calculate_reading_time(word_count)

        # Update timestamp
        update_data["updated_at"] = datetime.now(tz=UTC).replace(
            second=0,
            microsecond=0,
        )

        # Apply updates
        for key, value in update_data.items():
            setattr(db_blog, key, value)

        await self.session.flush()
        await self.session.refresh(db_blog)

        return db_blog

    async def delete(self, blog_id: UUID) -> bool:
        """
        Delete blog by ID.

        Args:
            blog_id: Blog UUID

        Returns:
            bool: True if blog was deleted, False if not found
        """
        db_blog = await self.get_by_id(blog_id)
        if not db_blog:
            return False

        await self.session.delete(db_blog)
        await self.session.flush()

        return True

    async def increment_view_count(self, blog_id: UUID) -> BlogDB | None:
        """
        Increment the view count of a blog.

        Args:
            blog_id: Blog UUID

        Returns:
            BlogDB | None: Updated blog if found, None otherwise
        """
        db_blog = await self.get_by_id(blog_id)
        if not db_blog:
            return None

        db_blog.view_count += 1
        await self.session.flush()
        await self.session.refresh(db_blog)

        return db_blog

    async def search_by_tags(
        self,
        tags: list[str],
        skip: int = 0,
        limit: int = 10,
    ) -> list[BlogDB]:
        """
        Search blogs by tags using PostgreSQL JSONB operators.

        Uses GIN index for efficient tag searching. Returns blogs that match
        any of the provided tags.

        Args:
            tags: List of tags to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[BlogDB]: List of blogs matching any of the tags
        """
        if not tags:
            return []

        # pyrefly: ignore [missing-attribute]
        tag_conditions = [func.jsonb_exists(BlogDB.tags.cast(JSONB), tag) for tag in tags]
        query = (
            select(BlogDB)
            .where(or_(*tag_conditions))
            # pyrefly: ignore [bad-argument-type]
            .order_by(desc(BlogDB.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        blogs = list(result.scalars().all())
        logger.info(f"Found {len(blogs)} blogs matching tags {tags}")
        return blogs

    async def search_by_tags_all(
        self,
        tags: list[str],
        skip: int = 0,
        limit: int = 10,
    ) -> list[BlogDB]:
        """
        Search blogs that contain ALL provided tags.

        Uses GIN index with containment operator for efficient searching.

        Args:
            tags: List of tags that must all be present
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            list[BlogDB]: List of blogs containing all specified tags
        """
        if not tags:
            return []

        query = (
            select(BlogDB)
            # pyrefly: ignore [missing-attribute]
            .where(BlogDB.tags.cast(JSONB).contains(tags))
            # pyrefly: ignore [bad-argument-type]
            .order_by(desc(BlogDB.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())
