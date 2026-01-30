"""
Blog model for the BaliBlissed application.

This module defines the Blog model used for representing blog posts
in the BaliBlissed application. Includes complete validation, security
features, and computed fields.
"""

from re import match, sub
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    computed_field,
    constr,
    field_validator,
    model_validator,
)

from app.utils.helpers import today_str


class AuthorResponse(BaseModel):
    """Author information for blog responses (without sensitive data)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID = Field(alias="id")
    username: str
    display_name: str = Field(alias="displayName")
    profile_picture: HttpUrl | None = Field(default=None, alias="profilePicture")


class BlogCreate(BaseModel):
    """Blog creation model (for request body - excludes auto-generated fields)."""

    model_config = ConfigDict(populate_by_name=True)

    author_id: UUID = Field(
        alias="authorId",
        description="Author ID (for foreign key relationship)",
    )
    title: Annotated[str, constr(min_length=1, max_length=100)] = Field(
        ...,
        description="Blog title",
        examples=["What to Pack for Your Bali Trip: The Essentials"],
    )
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Blog slug (auto-generated from title if not provided)",
        examples=["what-to-pack-for-your-bali-trip-the-essentials"],
    )
    summary: str | None = Field(
        default=None,
        max_length=300,
        description="Blog summary/excerpt (optional)",
    )
    content: Annotated[str, constr(min_length=10, max_length=50000)] = Field(
        ...,
        description="Blog content (markdown or plain text, min 50 words, 3 sentences)",
        examples=[
            """Packing for Bali can be tricky, but with the right preparation, you'll be ready for anything. The island's tropical climate means it's hot and humid year-round, so lightweight, breathable clothing is essential. However, you also need to be respectful when visiting temples and sacred sites, which means bringing modest clothing that covers your shoulders and knees. Don't forget essentials like sunscreen, insect repellent, and a reusable water bottle. Here's our complete packing list to make sure you're prepared for everything Bali has to offer.""",
        ],
    )
    tags: list[str] = Field(
        default=[],
        max_length=10,
        description="Blog tags for categorization",
        examples=[["travel", "bali", "packing"]],
    )
    images_url: list[HttpUrl] | None = Field(
        default=None,
        alias="imagesUrl",
        max_length=10,
        description="List of image URLs (max 10)",
    )
    videos_url: list[HttpUrl] | None = Field(
        default=None,
        alias="videosUrl",
        max_length=3,
        description="List of video URLs (max 3)",
    )
    status: Literal["draft", "published", "archived"] = Field(
        default="draft",
        description="Blog status",
        examples=["draft", "published", "archived"],
    )

    @model_validator(mode="before")
    @classmethod
    def generate_slug_from_title(cls, data: dict) -> dict:
        """Auto-generate slug from title if not provided."""
        # Handle both dict and object input
        if not isinstance(data, dict):
            data = dict(data)

        slug = data.get("slug")

        # If slug is provided and not empty, validate it
        if slug:
            if not match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
                mssg = "Slug must be lowercase alphanumeric with hyphens only"
                raise ValueError(mssg)
            return data

        # Generate from title
        title = data.get("title", "")
        if not title:
            mssg = "Title is required to generate slug"
            raise ValueError(mssg)

        generated_slug = title.lower()
        generated_slug = sub(r"[^a-z0-9\s-]", "", generated_slug)
        generated_slug = sub(r"\s+", "-", generated_slug)
        generated_slug = sub(r"-+", "-", generated_slug)
        generated_slug = generated_slug.strip("-")

        if not generated_slug:
            mssg = "Could not generate valid slug from title"
            raise ValueError(mssg)

        data["slug"] = generated_slug
        return data


class BlogSchema(BaseModel):
    """Blog model for representing blog posts (includes auto-generated fields)."""

    model_config = ConfigDict(populate_by_name=True)

    id: UUID = Field(default_factory=uuid4, description="Blog ID")
    author_id: UUID = Field(
        alias="authorId",
        description="Author ID (for foreign key relationship)",
    )
    title: Annotated[str, constr(min_length=1, max_length=100)] = Field(
        ...,
        description="Blog title",
        examples=["What to Pack for Your Bali Trip: The Essentials"],
    )
    slug: str = Field(
        default="",
        min_length=1,
        max_length=100,
        description="Blog slug (auto-generated from title)",
        examples=["what-to-pack-for-your-bali-trip-the-essentials"],
    )
    summary: str | None = Field(
        default=None,
        max_length=300,
        description="Blog summary/excerpt (optional)",
    )
    content: Annotated[str, constr(min_length=10, max_length=50000)] = Field(
        ...,
        description="Blog content (markdown or plain text, min 50 words, 3 sentences)",
        examples=[
            """Packing for Bali can be tricky, but with the right preparation, you'll be ready for anything. The island's tropical climate means it's hot and humid year-round, so lightweight, breathable clothing is essential. However, you also need to be respectful when visiting temples and sacred sites, which means bringing modest clothing that covers your shoulders and knees. Don't forget essentials like sunscreen, insect repellent, and a reusable water bottle. Here's our complete packing list to make sure you're prepared for everything Bali has to offer.""",
        ],
    )
    view_count: int = Field(
        default=0,
        ge=0,
        alias="viewCount",
        description="View count",
    )
    tags: list[str] = Field(
        default=[],
        max_length=10,
        description="Blog tags for categorization",
        examples=[["travel", "bali", "packing"]],
    )
    status: Literal["draft", "published", "archived"] = Field(
        default="draft",
        description="Blog status",
        examples=["draft", "published", "archived"],
    )
    images_url: list[HttpUrl] | None = Field(
        default=None,
        alias="imagesUrl",
        max_length=10,
        description="List of image URLs (max 10)",
    )
    videos_url: list[HttpUrl] | None = Field(
        default=None,
        alias="videosUrl",
        max_length=3,
        description="List of video URLs (max 3)",
    )
    created_at: str = Field(
        alias="createdAt",
        default_factory=today_str,
        description="Creation timestamp",
    )
    updated_at: str = Field(
        alias="updatedAt",
        default_factory=today_str,
        description="Last update timestamp",
    )

    @model_validator(mode="before")
    @classmethod
    def generate_slug_from_title(cls, data: dict) -> dict:
        """Auto-generate slug from title if not provided."""
        slug = data.get("slug", "")

        # If slug is provided and not empty, validate it
        if slug:
            if not match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
                mssg = "Slug must be lowercase alphanumeric with hyphens only"
                raise ValueError(mssg)
            return data

        # Generate from title
        title = data.get("title", "")
        if not title:
            mssg = "Title is required to generate slug"
            raise ValueError(mssg)

        generated_slug = title.lower()
        generated_slug = sub(r"[^a-z0-9\s-]", "", generated_slug)
        generated_slug = sub(r"\s+", "-", generated_slug)
        generated_slug = sub(r"-+", "-", generated_slug)
        generated_slug = generated_slug.strip("-")

        if not generated_slug:
            mssg = "Could not generate valid slug from title"
            raise ValueError(mssg)

        data["slug"] = generated_slug
        return data

    @field_validator("content", mode="after")
    @classmethod
    def validate_content_quality(cls, v: str) -> str:
        """Validate content quality (minimum sentences/structure)."""
        sentences = [s.strip() for s in v.split(".") if s.strip()]

        if len(sentences) < 3:
            mssg = "Content should have at least 3 sentences"
            raise ValueError(mssg)

        # Check for minimum word count
        word_count = len(v.split())
        if word_count < 50:
            mssg = "Content should have at least 50 words"
            raise ValueError(mssg)

        return v

    @field_validator("tags", mode="after")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags format."""
        if not v:
            return v

        # Check each tag
        for tag in v:
            if not 1 <= len(tag) <= 30:
                mssg = "Each tag must be 1-30 characters"
                raise ValueError(mssg)
            if not match(r"^[a-z0-9-]+$", tag.lower()):
                mssg = "Tags must be lowercase alphanumeric with hyphens only"
                raise ValueError(mssg)

        # Remove duplicates
        return list(set(v))

    @model_validator(mode="after")
    def validate_status_transition(self) -> "BlogSchema":
        """Validate status is valid (can be extended for transition logic)."""
        valid_statuses = {"draft", "published", "archived"}
        if self.status not in valid_statuses:
            mssg = f"Invalid status. Must be one of {valid_statuses}"
            raise ValueError(mssg)
        return self

    @computed_field
    @property
    def word_count(self) -> int:
        """Calculate word count."""
        return len(self.content.split())

    @computed_field
    @property
    def reading_time_minutes(self) -> int:
        """Calculate estimated reading time (average: 200 words/minute)."""
        return max(1, self.word_count // 200)


class BlogUpdate(BaseModel):
    """Blog update model (all fields optional)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Updated: Complete Guide to Bali Beaches",
                "summary": "An updated and comprehensive guide to the best beaches in Bali",
                "content": "This is an updated and much more comprehensive guide to Bali's beaches. Bali is renowned worldwide for its pristine beaches and crystal-clear waters. Whether you're a surfer looking for the perfect wave, a snorkeler wanting to explore vibrant coral reefs, or simply someone who wants to relax on soft sand, Bali has it all. This guide covers everything you need to know about the island's most spectacular coastal destinations.",
                "status": "archived",
                "tags": ["bali", "beaches", "travel", "guide", "updated"],
            },
        },
    )

    title: str | None = None
    slug: str | None = None
    summary: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    status: Literal["draft", "published", "archived"] | None = None
    images_url: list[HttpUrl] | None = None
    videos_url: list[HttpUrl] | None = None

    @field_validator("title", mode="before")
    @classmethod
    def validate_title_if_provided(cls, v: str | None) -> str | None:
        """Validate title if provided."""
        if v is None:
            return v
        if not 1 <= len(v) <= 100:
            mssg = "Title must be 1-100 characters"
            raise ValueError(mssg)
        return v

    @field_validator("content", mode="before")
    @classmethod
    def validate_content_if_provided(cls, v: str | None) -> str | None:
        """Validate content if provided."""
        if v is None:
            return v
        if not 10 <= len(v) <= 50000:
            mssg = "Content must be 10-50000 characters"
            raise ValueError(mssg)
        return v


class BlogResponse(BaseModel):
    """Blog response model (safe for API responses, without sensitive data)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    author_id: UUID = Field(alias="authorId")
    title: str
    slug: str
    summary: str | None = None
    content: str
    view_count: int = Field(alias="viewCount")
    word_count: int = Field(alias="wordCount")
    reading_time_minutes: int = Field(alias="readingTimeMinutes")
    tags: list[str]
    status: str
    images_url: list[HttpUrl] | None = Field(default=None, alias="imagesUrl")
    videos_url: list[HttpUrl] | None = Field(default=None, alias="videosUrl")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class BlogListResponse(BaseModel):
    """Blog list item response (lightweight for listing)."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    title: str
    slug: str
    summary: str | None = None
    view_count: int = Field(alias="viewCount")
    tags: list[str]
    status: str
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    reading_time_minutes: int = Field(alias="readingTimeMinutes")
