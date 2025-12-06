from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Additional error details")
    timestamp: str = Field(..., description="Error timestamp")
