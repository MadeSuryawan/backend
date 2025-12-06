from re import sub

from pydantic import BaseModel, EmailStr, Field, field_validator


class ContactInquiryRequest(BaseModel):
    """Model for contact form submissions."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,  # Using constant from settings
        description="The user's name",
        examples=["John Doe"],
    )
    email: EmailStr = Field(
        ...,
        description="The user's email address",
        examples=["johndoe@gmail.com"],
    )
    message: str = Field(
        ...,
        min_length=10,  # Using constant from settings
        max_length=2000,  # Using constant from settings
        description="The user's message",
        examples=["I would like to know more about your services."],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate and sanitize name input."""
        if not v or not v.strip():
            msg = "Name cannot be empty"
            raise ValueError(msg)
        # Remove potentially harmful characters
        sanitized = sub(r'[<>"\']', "", v.strip())
        if len(sanitized) < 1:
            msg = "Name must contain valid characters"
            raise ValueError(msg)
        return sanitized

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate and sanitize message input."""
        if not v or not v.strip():
            msg = "Message cannot be empty"
            raise ValueError(msg)
        # Remove potentially harmful characters but preserve basic formatting
        sanitized = sub(r"[<>]", "", v.strip())
        if len(sanitized) < 10:  # Using constant from settings
            msg = "Message must be at least 10 characters long"
            raise ValueError(msg)
        return sanitized


# --- Response Models ---


class ContactAnalysisResponse(BaseModel):
    """Response model for contact inquiry analysis."""

    confirmation: str = Field(..., description="Confirmation message for the user")
