"""Review database model using SQLModel."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from sqlmodel import Column, Field, ForeignKey, SQLModel, String


class ReviewDB(SQLModel, table=True):
    """
    Review database model for PostgreSQL.

    Represents user reviews for tour packages with ratings and images.
    Reviews can be:
    - Item-specific (item_id set) - Review for a specific tour package
    - Global (item_id is None) - General testimonial about the agency
    """

    __tablename__ = cast("declared_attr[str]", "reviews")

    __table_args__ = (
        Index("ix_reviews_user_item", "user_id", "item_id"),
        Index("ix_reviews_rating", "rating"),
        Index("ix_reviews_created_at", "created_at"),
    )

    # Primary key
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        nullable=False,
        description="Review ID",
    )

    # Foreign keys
    user_id: UUID = Field(
        sa_column=Column(
            "user_id",
            ForeignKey("users.uuid", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        description="Reviewer ID (foreign key to users.uuid)",
    )
    item_id: UUID | None = Field(
        default=None,
        sa_column=Column("item_id", nullable=True, index=True),
        description="Tour package ID (null for general testimonials)",
    )

    # Review content
    rating: int = Field(
        ge=1,
        le=5,
        description="Rating from 1-5 stars",
    )
    title: str | None = Field(
        default=None,
        sa_column=Column(String(100)),
        description="Review title (optional)",
    )
    content: str = Field(
        sa_column=Column(String(2000), nullable=False),
        description="Review content",
    )

    # Media fields (images only - no video for reviews)
    images_url: list[str] | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Review images (max 5)",
    )

    # Metadata
    is_verified_purchase: bool = Field(
        default=False,
        description="Whether reviewer actually purchased the item",
    )
    helpful_count: int = Field(
        default=0,
        ge=0,
        description="Number of users who found this helpful",
    )

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC).replace(second=0, microsecond=0),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Creation timestamp",
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
        description="Last update timestamp",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "item_id": None,
                "rating": 5,
                "title": "Amazing Bali Experience!",
                "content": "BaliBlissed made our honeymoon perfect...",
                "images_url": ["https://example.com/review1.jpg"],
                "is_verified_purchase": True,
                "helpful_count": 12,
            },
        },
    )

