"""
User model for authentication and authorization.

This module defines the User model used for authentication and authorization
in the BaliBlissed application.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    SecretStr,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

from app.utils.helpers import today_str


class UserCreate(BaseModel):
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
        examples=["johndoe"],
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
    email: EmailStr = Field(
        ...,
        description="Email address",
        examples=["johndoe@gmail.com"],
    )
    password: SecretStr = Field(
        ...,
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
    )
    phone_number: str | None = Field(
        alias="phoneNumber",
        default=None,
        pattern=r"^\+?1?\d{9,15}$",
        description="User phone number",
    )
    country: str | None = Field(default=None, description="User country")


class User(BaseModel):
    """User model for authentication and authorization (includes auto-generated fields)."""

    model_config = ConfigDict(
        populate_by_name=True,
        frozen=True,
        strict=True,
    )

    uuid: UUID = Field(alias="id", default_factory=uuid4, description="User ID")
    username: str = Field(
        ...,
        alias="userName",
        min_length=3,
        max_length=50,
        description="Username",
        examples=["johndoe"],
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
    email: EmailStr = Field(
        ...,
        description="Email address",
        examples=["johndoe@gmail.com"],
    )
    password: SecretStr = Field(..., description="Password", min_length=8)
    created_at: str = Field(
        alias="createdAt",
        default_factory=today_str,
        description="Creation timestamp",
    )
    updated_at: str | None = Field(
        alias="updatedAt",
        default=None,
        description="Last update timestamp",
    )
    is_active: bool = Field(
        alias="isActive",
        default=True,
        description="Whether the user is active",
    )
    is_verified: bool = Field(
        alias="isVerified",
        default=False,
        description="Whether the user is verified",
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
    )
    phone_number: str | None = Field(
        alias="phoneNumber",
        default=None,
        pattern=r"^\+?1?\d{9,15}$",
        description="User phone number",
    )
    country: str | None = Field(default=None, description="User country")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not (v.replace("_", "").replace("-", "")).isalnum():
            mssg = "Username must be alphanumeric. e.g. johndoe, john-doe, john_doe"
            raise ValueError(mssg)
        return v

    @field_validator("password", mode="before")
    @classmethod
    def validate_password_strength(cls, v: str | SecretStr) -> str | SecretStr:
        """Validate password strength."""
        # Handle both string and SecretStr inputs
        pwd = v.get_secret_value() if isinstance(v, SecretStr) else v
        if not any(c.isupper() for c in pwd):
            mssg = "Password must contain at least one uppercase letter"
            raise ValueError(mssg)
        if not any(c.isdigit() for c in pwd):
            mssg = "Password must contain at least one digit"
            raise ValueError(mssg)
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        """Validate email format."""
        try:
            # Pydantic's EmailStr validator will handle this
            return v
        except ValidationError as e:
            raise ValueError(str(e)) from e

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob(cls, v: str | datetime | None) -> str | None:
        """
        Validate date of birth and age constraints.

        Users must be between 17 and 80 years old (inclusive).
        """
        if v is None:
            return None

        now = datetime.now(tz=UTC)

        # Convert to datetime if string
        if isinstance(v, str):
            try:
                dob = datetime.fromisoformat(v)
                # Add UTC timezone if naive
                if dob.tzinfo is None:
                    dob = dob.replace(tzinfo=UTC)
            except ValueError as e:
                mssg = f"Invalid date format. Expected ISO format (YYYY-MM-DD): {e}"
                raise ValueError(mssg) from e
        elif isinstance(v, datetime):
            dob = v
            # Add UTC timezone if naive
            if dob.tzinfo is None:
                dob = dob.replace(tzinfo=UTC)
        else:
            mssg = f"Invalid type for date_of_birth. Expected str or datetime, got {type(v)}"
            raise TypeError(mssg)

        # Check if date is in the future
        if dob > now:
            mssg = "Date of birth cannot be in the future"
            raise ValueError(mssg)

        # Calculate age in years
        age_years = (now - dob).days / 365.25

        # Validate minimum age (17 years old)
        if age_years < 17:
            mssg = "User must be at least 17 years old"
            raise ValueError(mssg)

        # Validate maximum age (80 years old)
        if age_years > 80:
            mssg = "User must be at most 80 years old"
            raise ValueError(mssg)

        return dob.strftime("%Y-%m-%d")

    @field_validator("website", mode="before")
    @classmethod
    def validate_website(cls, v: str | None) -> str | None:
        """Validate website URL."""
        if v and not v.startswith(("http://", "https://")):
            return f"https://{v}"
        return v

    @computed_field
    @property
    def display_name(self) -> str:
        """Compute full name from first and last name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username


class UserUpdate(BaseModel):
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

    @field_validator("website", mode="before")
    @classmethod
    def validate_website(cls, v: str | None) -> str | None:
        """Validate website URL and auto-add https if missing."""
        if v and not v.startswith(("http://", "https://")):
            return f"https://{v}"
        return v

    @field_validator("password", mode="before")
    @classmethod
    def validate_password_strength(
        cls,
        v: str | SecretStr | None,
    ) -> str | SecretStr | None:
        """Validate password strength if password is provided."""
        if not v:
            return v
        # Handle both string and SecretStr inputs
        pwd = v.get_secret_value() if isinstance(v, SecretStr) else v
        if not any(c.isupper() for c in pwd):
            mssg = "Password must contain at least one uppercase letter"
            raise ValueError(mssg)
        if not any(c.isdigit() for c in pwd):
            mssg = "Password must contain at least one digit"
            raise ValueError(mssg)
        return v

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
    profile_picture: HttpUrl | None = Field(alias="profilePicture")
    bio: str = Field(default="N/A")
    website: HttpUrl | None = None
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    country: str = Field(default="N/A")

    @computed_field(alias="displayName")
    @property
    def display_name(self) -> str:
        """Compute full name from first and last name."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
