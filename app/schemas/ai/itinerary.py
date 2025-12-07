from re import sub

from pydantic import BaseModel, Field, field_validator

from app.configs.settings import (
    MAX_INTERESTS_COUNT,
    MAX_TRIP_DURATION,
    MIN_TRIP_DURATION,
)


class ItineraryRequest(BaseModel):
    """Model for travel itinerary generation requests."""

    destination: str = Field(
        default="Bali, Indonesia",  # Using constant from settings
        description="The travel destination",
        examples=["Bali, Indonesia"],
    )
    duration: int = Field(
        ...,
        ge=MIN_TRIP_DURATION,  # Using constant from settings
        le=MAX_TRIP_DURATION,  # Using constant from settings
        description="The duration of the trip in days",
        examples=[7],
    )
    interests: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_INTERESTS_COUNT,  # Using constant from settings
        description="A list of traveler's interests",
        examples=[["beaches", "temples", "food", "culture"]],
    )
    budget: str = Field(
        ...,
        description="The traveler's budget",
        examples=["$1000"],
    )

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v: str) -> str:
        """Validate and sanitize destination input."""
        if not v or not v.strip():
            msg = "Destination cannot be empty"
            raise ValueError(msg)
        # Remove potentially harmful characters
        sanitized = sub(r'[<>"\']', "", v.strip())
        if len(sanitized) < 1:
            msg = "Destination must contain valid characters"
            raise ValueError(msg)
        return sanitized

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, v: list[str]) -> list[str]:
        """Validate and sanitize interests list."""
        if not v:
            msg = "At least one interest must be provided"
            raise ValueError(msg)

        sanitized_interests = []
        for interest in v:
            if isinstance(interest, str) and interest.strip():
                # Remove potentially harmful characters and limit length
                sanitized = sub(r'[<>"\']', "", interest.strip())[:50]
                if sanitized:
                    sanitized_interests.append(sanitized)

        if not sanitized_interests:
            msg = "At least one valid interest must be provided"
            raise ValueError(msg)

        return sanitized_interests

    @field_validator("budget")
    @classmethod
    def validate_budget(cls, v: str) -> str:
        """Validate budget input."""
        if not v or not v.strip():
            msg = "Budget cannot be empty"
            raise ValueError(msg)
        return v


# --- Response Models ---


class ItineraryResponse(BaseModel):
    """Response model for itinerary generation."""

    itinerary: str = Field(..., description="Generated travel itinerary")
