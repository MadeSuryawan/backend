from pydantic import BaseModel, ConfigDict, Field


class DateTimeResponse(BaseModel):
    """
    Standard datetime representation in API responses.

    Provides multiple formats for datetime display:
    - utc: ISO 8601 format in UTC
    - local: User's local time with timezone abbreviation
    - human: Human-friendly relative time (e.g., "2 hours ago")
    - timezone: The timezone used for local conversion

    Examples:
        >>> dt_response = DateTimeResponse(
        ...     utc="2026-02-13T15:00:00Z",
        ...     local="2026-02-13 10:00:00 EST",
        ...     human="5 hours ago",
        ...     timezone="America/New_York"
        ... )

    """

    model_config = ConfigDict(ser_json_timedelta="iso8601", ser_json_bytes="utf8")

    utc: str = Field(
        ...,
        description="ISO 8601 UTC timestamp (e.g., '2026-02-13T15:00:00Z')",
    )
    local: str = Field(
        ...,
        description="User's local time with timezone abbreviation (e.g., '2026-02-13 10:00:00 EST')",
    )
    human: str = Field(
        ...,
        description="Human-friendly relative time (e.g., '2 hours ago', 'Yesterday')",
    )
    timezone: str = Field(
        ...,
        description="Timezone used for local conversion (e.g., 'America/New_York')",
    )
