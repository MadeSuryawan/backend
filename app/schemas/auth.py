from pydantic import BaseModel


class Token(BaseModel):
    """Token schema for JWT access tokens."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token data schema for extracted token payload."""

    username: str | None = None
