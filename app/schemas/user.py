"""
User model for authentication and authorization.

This module defines the User model used for authentication and authorization
in the BaliBlissed application.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError


class UserValidationMixin:
    """Shared validation logic for user models."""

    @field_validator("username", mode="after", check_fields=False)
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not (v.replace("_", "").replace("-", "")).isalnum():
            raise PydanticCustomError(
                "username_alphanumeric",
                "Username must be alphanumeric. e.g. johndoe, john-doe, john_doe",
            )
        return v

    @field_validator("password", mode="before", check_fields=False)
    @classmethod
    def validate_password_strength(
        cls,
        v: str | SecretStr | None,
    ) -> str | SecretStr | None:
        """Validate password strength."""
        if not v:
            return v
        pwd = v.get_secret_value() if isinstance(v, SecretStr) else v
        if not any(c.isupper() for c in pwd):
            raise PydanticCustomError(
                "password_uppercase",
                "Password must contain at least one uppercase letter",
            )
        if not any(c.isdigit() for c in pwd):
            raise PydanticCustomError(
                "password_digit",
                "Password must contain at least one digit",
            )
        return v

    @classmethod
    def _parse_dob(cls, v: str | datetime) -> datetime | None:
        """Parse date of birth into a UTC datetime object."""
        if isinstance(v, str):
            try:
                # Swagger often sends "string" as a default value
                if v == "string":
                    return None
                dob = datetime.fromisoformat(v)
            except ValueError:
                raise PydanticCustomError(
                    "dob_format",
                    "Invalid date format. Expected ISO format (YYYY-MM-DD)",
                ) from None
        elif isinstance(v, datetime):
            dob = v
        else:
            raise PydanticCustomError("dob_type", "Invalid type for date_of_birth")

        if dob and dob.tzinfo is None:
            dob = dob.replace(tzinfo=UTC)
        return dob

    @field_validator("date_of_birth", mode="before", check_fields=False)
    @classmethod
    def validate_dob(cls, v: str | datetime | None) -> str | None:
        """Validate date of birth and age constraints."""
        if v is None:
            return None
        # If empty string is passed, treat as None
        if isinstance(v, str) and not v.strip():
            return None

        dob = cls._parse_dob(v)
        if dob is None:
            return None

        now = datetime.now(tz=UTC)
        if dob > now:
            raise PydanticCustomError("dob_future", "Date of birth cannot be in the future")

        age = (now - dob).days / 365.25
        if age < 17:
            raise PydanticCustomError("age_min", "User must be at least 17 years old")
        if age > 80:
            raise PydanticCustomError("age_max", "User must be at most 80 years old")

        return dob.strftime("%Y-%m-%d")

    @field_validator("website", mode="before", check_fields=False)
    @classmethod
    def validate_website(cls, v: str | None) -> str | None:
        """Validate website URL."""
        if v and not v.startswith(("http://", "https://")):
            return f"https://{v}"
        return v


class UserCreate(UserValidationMixin, BaseModel):
    """User creation model (for request body - excludes auto-generated fields)."""

    model_config = ConfigDict(
        populate_by_name=True,
        frozen=True,
        strict=True,
    )

    username: str = Field(
        ...,
        alias="userName",
        min_length=3,
        max_length=50,
        description="Username",
        examples=["kusumasegara"],
    )
    first_name: str | None = Field(
        alias="firstName",
        default=None,
        description="User first name",
        examples=["Kusuma"],
    )
    last_name: str | None = Field(
        alias="lastName",
        default=None,
        description="User last name",
        examples=["Segara"],
    )
    email: EmailStr = Field(
        ...,
        description="Email address",
        examples=["kusumasegara000@gmail.com"],
    )
    password: SecretStr | None = Field(
        default=None,
        description="Password",
        min_length=8,
        examples=["Password123"],
    )
    profile_picture: HttpUrl | None = Field(
        alias="profilePicture",
        default=None,
        description="Profile picture URL",
    )
    bio: str | None = Field(
        default=None,
        description="User bio",
        max_length=160,
    )
    website: HttpUrl | None = Field(
        alias="website",
        default=None,
        description="User website",
    )
    date_of_birth: str | None = Field(
        alias="dateOfBirth",
        default=None,
        description="User date of birth",
    )
    gender: str | None = Field(
        default=None,
        description="User gender",
        examples=["Male"],
    )
    phone_number: str | None = Field(
        alias="phoneNumber",
        default=None,
        pattern=r"^\+?1?\d{9,15}$",
        description="User phone number",
    )
    country: str | None = Field(
        default=None,
        description="User country",
        examples=["Indonesia"],
    )


class UserUpdate(UserValidationMixin, BaseModel):
    """User update model for profile changes."""

    model_config = ConfigDict(
        populate_by_name=True,
        frozen=True,
        strict=True,
    )

    first_name: str | None = Field(
        alias="firstName",
        default=None,
        description="User first name",
    )
    last_name: str | None = Field(
        alias="lastName",
        default=None,
        description="User last name",
    )
    email: EmailStr | None = Field(
        default=None,
        description="Email address",
        examples=["johndoe@gmail.com"],
    )
    password: SecretStr | None = Field(
        default=None,
        description="New password",
        min_length=8,
    )
    confirmed_password: SecretStr | None = Field(
        default=None,
        description="Confirmed new password",
    )
    bio: str | None = Field(
        default=None,
        description="User bio",
        max_length=160,
    )
    website: HttpUrl | None = Field(
        default=None,
        description="User website",
    )
    phone_number: str | None = Field(
        alias="phoneNumber",
        default=None,
        pattern=r"^\+?1?\d{9,15}$",
        description="User phone number",
    )
    country: str | None = Field(
        default=None,
        description="User country",
    )

    @model_validator(mode="after")
    def validate_password_match(self) -> "UserUpdate":
        """Validate password and confirmed password match."""
        if self.password or self.confirmed_password:
            if not self.password:
                mssg = "Password is required when confirming password"
                raise ValueError(mssg)
            if not self.confirmed_password:
                mssg = "Confirmed password is required when changing password"
                raise ValueError(mssg)
            if self.password.get_secret_value() != self.confirmed_password.get_secret_value():
                mssg = "Password and confirmed password must match"
                raise ValueError(mssg)
        return self


class TestimonialUpdate(BaseModel):
    """Testimonial update model for user testimonial."""

    model_config = ConfigDict(populate_by_name=True)

    testimonial: str | None = Field(
        default=None,
        max_length=500,
        description="User testimonial or review text",
        examples=[
            "I had an amazing experience with BaliBlissed. The tour package was well-organized, and the guides were knowledgeable and friendly. The temples and beaches were breathtaking, and I would highly recommend this company to anyone planning a trip to Bali.",
        ],
    )


class UserResponse(BaseModel):
    """User response model (without sensitive information)."""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

    uuid: UUID = Field(alias="id")
    username: str
    first_name: str = Field(default="N/A", alias="firstName")
    last_name: str = Field(default="N/A", alias="lastName")
    email: EmailStr
    is_active: bool = Field(alias="isActive")
    is_verified: bool = Field(alias="isVerified")
    role: str = Field(default="user", description="User role (user, moderator, admin)")
    profile_picture: HttpUrl | str | None = Field(alias="profilePicture")
    bio: str = Field(default="N/A")
    website: HttpUrl | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    country: str = Field(default="N/A")
    display_name: str | None = Field(
        default=None,
        alias="displayName",
        description="Display name (stored in database, computed if missing)",
    )
    testimonial: str | None = Field(
        default=None,
        description="User testimonial or review text",
    )

    @field_validator("first_name", "last_name", "bio", "country", mode="before")
    @classmethod
    def none_to_default(cls, v: Any, info: Any) -> Any:  # noqa: ANN401
        """Convert None to default value if field has one."""
        if v is None:
            # Pydantic v2 doesn't easily expose 'default' in validator context cleanly for this
            # without inspecting model_fields.
            # Simplified: just return "N/A" as that's the default for all these fields.
            return "N/A"
        return v

    @model_validator(mode="after")
    def compute_display_name_if_missing(self) -> "UserResponse":
        """
        Compute display_name if not provided (fallback for backward compatibility).

        This ensures display_name is always set, even if the database value is None
        (shouldn't happen after migration, but provides safety).
        """
        if not self.display_name:
            if (
                self.first_name
                and self.last_name
                and self.first_name != "N/A"
                and self.last_name != "N/A"
            ):
                self.display_name = f"{self.first_name} {self.last_name}"
            else:
                self.display_name = self.username
        return self
