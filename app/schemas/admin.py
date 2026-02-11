"""Admin-related schemas for administrative operations."""

from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class AdminUserResponse(UserResponse):
    """Extended user response for admin views with role information."""

    role: str = Field(..., description="User role (user, moderator, admin)")
    is_verified: bool = Field(default=False, description="Whether the user is verified")


class AdminUserListResponse(BaseModel):
    """Paginated list of users for admin interface."""

    users: list[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users in database")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum number of records returned")


class UserRoleUpdate(BaseModel):
    """Request schema for updating user role."""

    role: str = Field(
        ...,
        description="New role (user, moderator, admin)",
        pattern="^(user|moderator|admin)$",
    )


class UserVerificationUpdate(BaseModel):
    """Request schema for updating user verification status."""

    status: bool = Field(
        ...,
        description="New verification status (true, false)",
        examples=[True, False],
    )


class SystemStatsResponse(BaseModel):
    """System statistics response for admin dashboard."""

    total_users: int = Field(..., description="Total number of users")
    verified_users: int = Field(..., description="Number of verified users")
    admin_users: int = Field(..., description="Number of admin users")
    moderator_users: int = Field(..., description="Number of moderator users")
