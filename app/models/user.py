"""User database model using SQLModel."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from pydantic import ConfigDict
from sqlalchemy import DateTime
from sqlalchemy.orm import declared_attr
from sqlmodel import Column, Field, SQLModel, String


class UserDB(SQLModel, table=True):
    """
    User database model for PostgreSQL.

    This model represents the users table in the database.
    It includes all fields from the User schema with proper database types.
    """

    __tablename__ = cast("declared_attr[str]", "users")

    # Primary key
    uuid: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        nullable=False,
        description="User ID",
    )

    # Required fields
    username: str = Field(
        sa_column=Column(String(50), unique=True, nullable=False, index=True),
        description="Username (unique)",
    )
    email: str = Field(
        sa_column=Column(String(255), unique=True, nullable=False, index=True),
        description="Email address (unique)",
    )
    password_hash: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
        description="Hashed password (null for OAuth users)",
    )
    auth_provider: str = Field(
        default="email",
        sa_column=Column(String(50), nullable=False, server_default="email"),
        description="Auth provider (email, google, wechat)",
    )
    provider_id: str | None = Field(
        default=None,
        sa_column=Column(String(255), nullable=True, index=True),
        description="Provider specific ID",
    )

    # Optional profile fields
    first_name: str | None = Field(
        default=None,
        sa_column=Column(String(100)),
        description="User first name",
    )
    last_name: str | None = Field(
        default=None,
        sa_column=Column(String(100)),
        description="User last name",
    )
    display_name: str | None = Field(
        default=None,
        sa_column=Column(String(200)),
        description="Computed display name (first_name + last_name or username)",
    )
    bio: str | None = Field(
        default=None,
        sa_column=Column(String(160)),
        description="User bio (max 160 chars)",
    )
    profile_picture: str | None = Field(
        default=None,
        sa_column=Column(String(500)),
        description="Profile picture URL",
    )
    website: str | None = Field(
        default=None,
        sa_column=Column(String(500)),
        description="User website URL",
    )
    date_of_birth: str | None = Field(
        default=None,
        sa_column=Column(String(10)),
        description="Date of birth (YYYY-MM-DD)",
    )
    gender: str | None = Field(
        default=None,
        sa_column=Column(String(50)),
        description="User gender",
    )
    phone_number: str | None = Field(
        default=None,
        sa_column=Column(String(20)),
        description="Phone number",
    )
    country: str | None = Field(
        default=None,
        sa_column=Column(String(100)),
        description="User country",
    )

    # Status fields
    is_verified: bool = Field(
        default=False,
        nullable=False,
        description="Whether the user is verified",
    )

    # Role-based access control
    role: str = Field(
        default="user",
        sa_column=Column(String(20), nullable=False, server_default="user", index=True),
        description="User role (user, moderator, admin)",
    )

    # Testimonial
    testimonial: str | None = Field(
        default=None,
        sa_column=Column(String(500)),
        description="User testimonial or review text",
    )

    # Timestamps (timezone-aware)
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
        json_schema_extra={
            "example": {
                "uuid": "123e4567-e89b-12d3-a456-426614174000",
                "username": "johndoe",
                "email": "johndoe@gmail.com",
                "first_name": "John",
                "last_name": "Doe",
                "is_verified": False,
                "role": "user",
                "testimonial": "Great service!",
            },
        },
    )
