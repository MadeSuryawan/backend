"""
Review schemas for the BaliBlissed application.

This module defines the Review schemas used for representing user reviews
in the BaliBlissed application.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.schemas.datetime import DateTimeResponse


class ReviewCreate(BaseModel):
    """Review creation model (for request body)."""

    model_config = ConfigDict(populate_by_name=True)

    item_id: UUID | None = Field(
        default=None,
        alias="itemId",
        description="Tour package ID (null for general testimonials)",
    )
    rating: int = Field(
        ge=1,
        le=5,
        description="Rating from 1-5 stars",
    )
    title: str | None = Field(
        default=None,
        max_length=100,
        description="Review title (optional)",
    )
    content: str = Field(
        min_length=10,
        max_length=2000,
        description="Review content",
        examples=[
            "I had an amazing experience with BaliBlissed. The tour package was well-organized, and the guides were knowledgeable and friendly. The temples and beaches were breathtaking, and I would highly recommend this company to anyone planning a trip to Bali.",
        ],
    )

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        """Validate rating is between 1 and 5."""
        if not 1 <= v <= 5:
            msg = "Rating must be between 1 and 5"
            raise ValueError(msg)
        return v


class ReviewUpdate(BaseModel):
    """Review update model (all fields optional)."""

    model_config = ConfigDict(populate_by_name=True)

    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = Field(default=None, max_length=100)
    content: str | None = Field(default=None, min_length=10, max_length=2000)


class ReviewResponse(BaseModel):
    """Review response model (safe for API responses)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    user_id: UUID = Field(alias="userId")
    item_id: UUID | None = Field(default=None, alias="itemId")
    rating: int
    title: str | None = None
    content: str
    images_url: list[HttpUrl] | None = Field(default=None, alias="imagesUrl")
    is_verified_purchase: bool = Field(alias="isVerifiedPurchase")
    helpful_count: int = Field(alias="helpfulCount")
    created_at: DateTimeResponse | datetime = Field(alias="createdAt")
    updated_at: DateTimeResponse | datetime | None = Field(default=None, alias="updatedAt")


class ReviewListResponse(BaseModel):
    """Review list item response (lightweight for listing)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    user_id: UUID = Field(alias="userId")
    rating: int
    title: str | None = None
    content: str
    is_verified_purchase: bool = Field(alias="isVerifiedPurchase")
    helpful_count: int = Field(alias="helpfulCount")
    created_at: DateTimeResponse | datetime = Field(alias="createdAt")


class MediaUploadResponse(BaseModel):
    """Response for media upload operations."""

    model_config = ConfigDict(populate_by_name=True)

    media_id: str = Field(alias="mediaId", description="ID of uploaded media")
    url: HttpUrl | str = Field(description="URL of the uploaded media")
    media_type: str | None = Field(
        default=None,
        alias="mediaType",
        description="Type of media (image/video)",
    )
