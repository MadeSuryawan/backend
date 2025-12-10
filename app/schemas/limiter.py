from pydantic import BaseModel, ConfigDict, Field


class LimiterResetRequest(BaseModel):
    """Request model for resetting rate limits."""

    key: str = ""
    all_endpoints: bool = False

    model_config = ConfigDict(extra="forbid")


class LimiterResetResponse(BaseModel):
    """Response model for resetting rate limits."""

    message: str
    count: int
    identifier: str

    model_config = ConfigDict(extra="forbid")


class LimiterHealthResponse(BaseModel):
    """Response model for health check."""

    storage: str = Field(default="redis")
    healthy: bool = Field(default=True)
    detail: str = Field(default="Using shared Redis instance")

    model_config = ConfigDict(extra="forbid")
