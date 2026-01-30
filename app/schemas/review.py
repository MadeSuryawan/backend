"""
Review schemas for the BaliBlissed application.

This module defines the Review schemas used for representing user reviews
in the BaliBlissed application.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


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
    created_at: str = Field(alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


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
    created_at: str = Field(alias="createdAt")


class MediaUploadResponse(BaseModel):
    """Response for media upload operations."""

    model_config = ConfigDict(populate_by_name=True)

    url: HttpUrl = Field(description="URL of the uploaded media")
    media_type: str = Field(alias="mediaType", description="Type of media (image/video)")

