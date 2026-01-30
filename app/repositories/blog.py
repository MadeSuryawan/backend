"""Blog repository for database operations."""

from datetime import UTC, datetime
from logging import getLogger
from typing import Any, Literal, cast
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.expression import ColumnElement

from app.errors.database import DuplicateEntryError
from app.models.blog import BlogDB
from app.repositories.base import BaseRepository
from app.schemas.blog import BlogSchema, BlogUpdate
from app.utils.helpers import file_logger

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


class BlogRepository(BaseRepository[BlogDB, BlogSchema, BlogUpdate]):
    """
    Repository for Blog database operations.

    This class implements the repository pattern for Blog entities,
    providing CRUD operations and business logic.
    """

    model = BlogDB

    def __init__(self, session: AsyncSession) -> None:
        """
        Initialize repository with database session.

        Args:
            session: Async database session
        """
        super().__init__(session)

    async def create(
        self,
        schema: BlogSchema,
        author_id: UUID | None = None,
        **kwargs: dict[str, Any],
    ) -> BlogDB:
        """
        Create a new blog post in the database.

        Args:
            schema: Blog schema with blog data
            author_id: UUID of the blog author (required, but optional in signature to match base)
            **kwargs: Additional arguments

        Returns:
            BlogDB: Created blog database model

        Raises:
            DuplicateEntryError: If slug already exists
            DatabaseError: For other database errors
            ValueError: If author_id is missing
        """
        if author_id is None:
            detail = "author_id is required for creating a blog"
            raise ValueError(detail)

        word_count = calculate_word_count(schema.content)
        reading_time = calculate_reading_time(word_count)

        db_blog = BlogDB(
            author_id=author_id,
            title=schema.title,
            slug=schema.slug,
            content=schema.content,
            summary=schema.summary,
            view_count=0,
            word_count=word_count,
            reading_time_minutes=reading_time,
            status=schema.status if hasattr(schema, "status") and schema.status else "draft",
            tags=schema.tags,
            images_url=[str(url) for url in schema.images_url] if schema.images_url else None,
            videos_url=[str(url) for url in schema.videos_url] if schema.videos_url else None,
            created_at=datetime.now(tz=UTC).replace(second=0, microsecond=0),
            updated_at=datetime.now(tz=UTC).replace(second=0, microsecond=0),
        )

        try:
            return await self._add_and_refresh(db_blog)
        except DuplicateEntryError as e:
            # Re-raise with friendlier message if it's a slug conflict
            if "slug" in str(e):
                raise DuplicateEntryError(
                    detail=f"Blog with slug '{schema.slug}' already exists",
                ) from e
            raise

    async def get_by_slug(self, slug: str) -> BlogDB | None:
        """
        Get blog by slug.

        Args:
            slug: Blog slug

        Returns:
            BlogDB | None: Blog if found, None otherwise
        """
        return await self.get_by_field("slug", slug)

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
            query = query.where(cast(ColumnElement[bool], BlogDB.status == status))
        if author_id:
            query = query.where(cast(ColumnElement[bool], BlogDB.author_id == author_id))

        # Apply pagination and ordering
        query = (
            query.order_by(desc(cast(ColumnElement[datetime], BlogDB.created_at)))
            .offset(skip)
            .limit(limit)
        )

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

    async def update(self, record_id: UUID, schema: BlogUpdate) -> BlogDB | None:
        """
        Update blog information.

        Args:
            record_id: Blog UUID
            schema: Blog update schema with fields to update

        Returns:
            BlogDB | None: Updated blog if found, None otherwise

        Raises:
            ValueError: If slug already exists for another blog
        """
        db_blog = await self.get_by_id(record_id)
        if not db_blog:
            return None

        # Check if slug is being updated and already exists
        if schema.slug:
            existing_blog = await self.get_by_slug(schema.slug)
            if existing_blog and existing_blog.id != record_id:
                msg = f"Slug '{schema.slug}' already exists"
                raise ValueError(msg)

        # Update fields
        update_data = schema.model_dump(exclude_unset=True, exclude_none=True)

        # Convert image URLs to strings
        if "images_url" in update_data and update_data["images_url"]:
            update_data["images_url"] = [str(url) for url in update_data["images_url"]]

        # Convert video URLs to strings
        if "videos_url" in update_data and update_data["videos_url"]:
            update_data["videos_url"] = [str(url) for url in update_data["videos_url"]]

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

        for key, value in update_data.items():
            setattr(db_blog, key, value)

        return await self._add_and_refresh(db_blog)

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
        return await self._add_and_refresh(db_blog)

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

        tag_conditions = [
            func.jsonb_exists(cast(ColumnElement, BlogDB.tags).cast(JSONB), tag) for tag in tags
        ]
        query = (
            select(BlogDB)
            .where(or_(*tag_conditions))
            .order_by(desc(cast(ColumnElement[datetime], BlogDB.created_at)))
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
            .where(cast(ColumnElement, BlogDB.tags).cast(JSONB).contains(tags))
            .order_by(desc(cast(ColumnElement[datetime], BlogDB.created_at)))
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def add_image(self, blog_id: UUID, image_url: str) -> BlogDB | None:
        """
        Add an image URL to a blog's images_url list.

        Args:
            blog_id: Blog UUID
            image_url: URL of the uploaded image

        Returns:
            BlogDB | None: Updated blog or None if not found
        """
        blog = await self.get_by_id(blog_id)
        if not blog:
            return None

        current_images = blog.images_url or []
        blog.images_url = [*current_images, image_url]
        blog.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(blog)
        return blog

    async def add_video(self, blog_id: UUID, video_url: str) -> BlogDB | None:
        """
        Add a video URL to a blog's videos_url list.

        Args:
            blog_id: Blog UUID
            video_url: URL of the uploaded video

        Returns:
            BlogDB | None: Updated blog or None if not found
        """
        blog = await self.get_by_id(blog_id)
        if not blog:
            return None

        current_videos = blog.videos_url or []
        blog.videos_url = [*current_videos, video_url]
        blog.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(blog)
        return blog

    async def remove_image(self, blog_id: UUID, image_url: str) -> BlogDB | None:
        """
        Remove an image URL from a blog's images_url list.

        Args:
            blog_id: Blog UUID
            image_url: URL of the image to remove

        Returns:
            BlogDB | None: Updated blog or None if not found
        """
        blog = await self.get_by_id(blog_id)
        if not blog:
            return None

        images = blog.images_url or []
        if image_url in images:
            images.remove(image_url)
            blog.images_url = images if images else None
            blog.updated_at = datetime.now(UTC)

            await self.session.commit()
            await self.session.refresh(blog)

        return blog

    async def remove_video(self, blog_id: UUID, video_url: str) -> BlogDB | None:
        """
        Remove a video URL from a blog's videos_url list.

        Args:
            blog_id: Blog UUID
            video_url: URL of the video to remove

        Returns:
            BlogDB | None: Updated blog or None if not found
        """
        blog = await self.get_by_id(blog_id)
        if not blog:
            return None

        videos = blog.videos_url or []
        if video_url in videos:
            videos.remove(video_url)
            blog.videos_url = videos if videos else None
            blog.updated_at = datetime.now(UTC)

            await self.session.commit()
            await self.session.refresh(blog)

        return blog
