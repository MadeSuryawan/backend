from re import sub

from google.genai.types import Part
from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    """Model for individual chat messages in conversation history."""

    role: str = Field(
        ...,
        description="The role of the message sender",
        examples=["user"],
    )
    parts: list[Part] = Field(
        ...,
        description="The message content parts",
        examples=[[Part(text="Hello, how are you?")]],
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate message role."""
        allowed_roles = {"user", "assistant", "system"}
        if v not in allowed_roles:
            msg = f"Role must be one of: {allowed_roles}"
            raise ValueError(msg)
        return v


class ChatRequest(BaseModel):
    """Model for user query requests."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,  # Using constant from settings
        description="The user's query",
        examples=["What are the best beaches in Bali?"],
    )
    history: list[ChatMessage] = Field(
        default=[],
        max_length=50,  # Limit conversation history
        description="The chat history",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query input."""

        if not v or not v.strip():
            msg = "Query cannot be empty"
            raise ValueError(msg)

        # Remove potentially harmful characters
        sanitized = sub(r'[<>"\']', "", v.strip())
        if len(sanitized) < 1:
            msg = "Query must contain valid characters"
            raise ValueError(msg)
        return sanitized


# --- Response Models ---


class ChatResponse(BaseModel):
    """Response model for query processing."""

    answer: dict[str, str] = Field(..., description="AI-generated response to the query")
