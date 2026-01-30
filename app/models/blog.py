"""Blog database model using SQLModel."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlmodel import Column, Field, ForeignKey, SQLModel, String


class BlogDB(SQLModel, table=True):
    """
    Blog database model for PostgreSQL.

    This model represents the blogs table in the database.
    It includes all fields from the Blog schema with proper database types
    and a foreign key relationship to the User model.
    """

    __tablename__ = cast("declared_attr[str]", "blogs")

    __table_args__ = (
        Index("ix_blogs_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_blogs_status_created", "status", "created_at"),
        Index("ix_blogs_author_status", "author_id", "status"),
    )

    # Primary key
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        nullable=False,
        description="Blog ID",
    )

    # Foreign key to User
    author_id: UUID = Field(
        sa_column=Column(
            "author_id",
            ForeignKey("users.uuid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="Author ID (foreign key to users.uuid)",
    )

    # Required fields
    title: str = Field(
        sa_column=Column(String(100), nullable=False),
        description="Blog title",
    )
    slug: str = Field(
        sa_column=Column(String(100), unique=True, nullable=False, index=True),
        description="URL-friendly slug (unique)",
    )
    content: str = Field(
        sa_column=Column(String(50000), nullable=False),
        description="Blog content (markdown or plain text)",
    )

    # Optional fields
    summary: str | None = Field(
        default=None,
        sa_column=Column(String(300)),
        description="Blog summary/excerpt",
    )

    # Metadata fields
    view_count: int = Field(
        default=0,
        nullable=False,
        description="View count",
    )
    word_count: int = Field(
        default=0,
        nullable=False,
        description="Word count of the content",
    )
    reading_time_minutes: int = Field(
        default=0,
        nullable=False,
        description="Estimated reading time in minutes",
    )
    status: str = Field(
        default="draft",
        sa_column=Column(String(20), nullable=False, index=True),
        description="Blog status (draft, published, archived)",
    )

    # Array fields (stored as JSON in PostgreSQL)
    tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
        description="Blog tags for categorization",
    )
    images_url: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="List of image URLs (max 10)",
    )
    videos_url: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="List of video URLs (max 3)",
    )

    # Timestamps (timezone-aware)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC).replace(second=0, microsecond=0),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="Creation timestamp",
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last update timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "author_id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "Ultimate Bali Travel Guide 2024",
                "slug": "ultimate-bali-travel-guide-2024",
                "content": "Bali is a beautiful island...",
                "summary": "Everything you need to know about traveling to Bali",
                "view_count": 0,
                "status": "draft",
                "tags": ["travel", "bali", "guide"],
                "images_url": ["https://example.com/bali1.jpg"],
            },
        },
    )
