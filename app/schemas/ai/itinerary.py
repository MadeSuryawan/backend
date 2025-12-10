# app/schemas/ai/itinerary.py

"""
Schemas for AI-powered itinerary generation requests and responses.

This module provides Pydantic models with comprehensive validation to ensure
realistic itinerary combinations of budget, duration, and interests.
"""

from re import sub
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.configs.settings import (
    MAX_INTERESTS_COUNT,
    MAX_TRIP_DURATION,
    MIN_TRIP_DURATION,
)

# --- Budget Validation Constants ---
# Minimum budget allowed (matching frontend constraint)
MIN_BUDGET_USD = 300

# Cost calculation factors for realistic itinerary validation
# Base daily cost covers accommodation, basic meals, and transportation
BASE_DAILY_COST_USD = 50

# Additional cost per interest per day (activities, entrance fees, etc.)
COST_PER_INTEREST_USD = 25

# Minimum buffer percentage to ensure comfortable trip (20%)
BUDGET_BUFFER_PERCENTAGE = 0.20


def extract_budget_amount(budget_str: str) -> float:
    """
    Extract numeric value from budget string.

    Args:
        budget_str: Budget string in format like "US$ 1000" or "$1,500"

    Returns:
        The numeric budget value as float

    Raises:
        ValueError: If no valid numeric value can be extracted
    """
    # Remove currency symbols and common formatting
    cleaned = sub(r"[US$,\s]", "", budget_str.upper())
    # Handle potential remaining non-numeric characters except decimal point
    cleaned = sub(r"[^\d.]", "", cleaned)

    if not cleaned:
        msg = "Could not extract budget amount from the provided value"
        raise ValueError(msg)

    return float(cleaned)


def calculate_minimum_required_budget(duration: int, interests_count: int) -> float:
    """
    Calculate the minimum budget required for a trip.

    The formula considers:
    - Base daily costs (accommodation, meals, transport)
    - Additional costs per interest (activities, tours, entrance fees)
    - A buffer for unexpected expenses

    Args:
        duration: Trip duration in days
        interests_count: Number of interests/activities

    Returns:
        Minimum required budget in USD
    """
    base_cost = duration * BASE_DAILY_COST_USD
    interest_cost = duration * interests_count * COST_PER_INTEREST_USD
    subtotal = base_cost + interest_cost
    buffer = subtotal * BUDGET_BUFFER_PERCENTAGE
    return subtotal + buffer


def calculate_max_duration_for_budget(budget: float, interests_count: int) -> int:
    """
    Calculate maximum trip duration for a given budget.

    Args:
        budget: Available budget in USD
        interests_count: Number of interests/activities

    Returns:
        Maximum trip duration in days that the budget can support
    """
    # daily_cost = BASE_DAILY_COST_USD + (interests_count * COST_PER_INTEREST_USD)
    # With buffer: total = days * daily_cost * (1 + BUDGET_BUFFER_PERCENTAGE)
    daily_cost_with_buffer = (BASE_DAILY_COST_USD + (interests_count * COST_PER_INTEREST_USD)) * (
        1 + BUDGET_BUFFER_PERCENTAGE
    )

    return int(budget / daily_cost_with_buffer)


def calculate_max_interests_for_budget(budget: float, duration: int) -> int:
    """
    Calculate maximum interests for a given budget and duration.

    Args:
        budget: Available budget in USD
        duration: Trip duration in days

    Returns:
        Maximum number of interests the budget can support
    """
    # budget = duration * (BASE_DAILY_COST_USD + interests * COST_PER_INTEREST_USD)
    #           * (1 + BUDGET_BUFFER_PERCENTAGE)
    base_total = duration * BASE_DAILY_COST_USD * (1 + BUDGET_BUFFER_PERCENTAGE)
    remaining = budget - base_total
    cost_per_interest_with_buffer = (
        duration * COST_PER_INTEREST_USD * (1 + BUDGET_BUFFER_PERCENTAGE)
    )

    if remaining <= 0:
        return 0

    return int(remaining / cost_per_interest_with_buffer)


class ItineraryRequestMD(BaseModel):
    """
    Model for travel itinerary generation requests.

    This model validates individual fields and performs cross-field validation
    to ensure the combination of budget, duration, and interests creates a
    realistic and feasible travel itinerary.

    Validation Rules:
        - Duration: 1-30 days
        - Interests: 1-4 items
        - Budget: Minimum $300 USD
        - Cross-validation: Budget must be sufficient for duration × interests

    Example:
        >>> request = ItineraryRequestMD(
        ...     duration=7,
        ...     interests=["beaches", "temples"],
        ...     budget="US$ 1000"
        ... )
    """

    duration: int = Field(
        ...,
        ge=MIN_TRIP_DURATION,
        le=MAX_TRIP_DURATION,
        description="The duration of the trip in days",
        examples=[7],
    )
    interests: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_INTERESTS_COUNT,
        description="A list of traveler's interests",
        examples=[["beaches", "temples", "food", "culture"]],
    )
    budget: str = Field(
        ...,
        description="The traveler's budget in USD",
        examples=["US$ 1000"],
    )

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, v: list[str]) -> list[str]:
        """
        Validate and sanitize interests list.

        Args:
            v: List of interest strings

        Returns:
            Sanitized list of interests

        Raises:
            ValueError: If no valid interests are provided
        """
        if not v:
            msg = "At least one interest must be provided"
            raise ValueError(msg)

        sanitized_interests = []
        for interest in v:
            if isinstance(interest, str) and interest.strip():
                # Remove potentially harmful characters and limit length
                sanitized = sub(r"[<>\"']", "", interest.strip())[:50]
                if sanitized:
                    sanitized_interests.append(sanitized)

        if not sanitized_interests:
            msg = "At least one valid interest must be provided"
            raise ValueError(msg)

        return sanitized_interests

    @field_validator("budget")
    @classmethod
    def validate_budget_format(cls, v: str) -> str:
        """
        Validate and normalize budget input format.

        Args:
            v: Budget string in various formats

        Returns:
            Normalized budget string in "US$ X" format

        Raises:
            ValueError: If budget is empty or below minimum
        """
        if not v or not v.strip():
            msg = "Budget cannot be empty"
            raise ValueError(msg)

        v = v.strip()

        # Normalize format
        if not v.upper().startswith("US$"):
            v = f"US{v}" if v.startswith("$") else f"US$ {v}"

        # Validate minimum budget
        amount = extract_budget_amount(v)
        if amount < MIN_BUDGET_USD:
            msg = f"Budget must be at least US$ {MIN_BUDGET_USD}"
            raise ValueError(msg)

        return v

    @model_validator(mode="after")
    def validate_budget_feasibility(self) -> Self:
        """
        Validate that budget is sufficient for the trip configuration.

        This cross-field validator ensures the combination of duration,
        interests, and budget creates a realistic travel itinerary.

        Returns:
            Self: Validated model instance

        Raises:
            ValueError: If budget is insufficient for the trip configuration
        """
        budget_amount = extract_budget_amount(self.budget)
        interests_count = len(self.interests)
        required_budget = calculate_minimum_required_budget(self.duration, interests_count)

        if budget_amount < required_budget:
            # Calculate what's achievable with current budget
            max_duration = calculate_max_duration_for_budget(budget_amount, interests_count)
            max_interests = calculate_max_interests_for_budget(budget_amount, self.duration)

            # Build helpful error message with suggestions
            suggestions = []
            if max_duration >= MIN_TRIP_DURATION:
                suggestions.append(f"reduce duration to {max_duration} days")
            if max_interests >= 1:
                suggestions.append(f"reduce interests to {max_interests}")
            suggestions.append(f"increase budget to at least US$ {required_budget:.0f}")

            suggestion_text = " or ".join(suggestions)

            msg = (
                f"Budget of US$ {budget_amount:.0f} is insufficient for a "
                f"{self.duration}-day trip with {interests_count} interests. "
                f"Minimum required: US$ {required_budget:.0f}. "
                f"Suggestions: {suggestion_text}."
            )
            raise ValueError(msg)

        return self


class ItineraryRequestTXT(BaseModel):
    user_name: str = Field(..., description="User name")
    md_id: UUID = Field(..., description="Markdown itinerary id")
    itinerary_md: str = Field(..., description="Markdown itinerary source")


# --- Response Models ---


class ItineraryMD(BaseModel):
    """Response model for itinerary generation."""

    itinerary: str = Field(..., description="Generated markdown travel itinerary")


class ItineraryTXT(BaseModel):
    """API Response model including WhatsApp-friendly text."""

    text_content: str = Field(..., description="WhatsApp-friendly plain text version")
