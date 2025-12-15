"""Admin-related schemas for administrative operations."""


from pydantic import BaseModel, Field

from app.schemas.user import UserResponse


class AdminUserResponse(UserResponse):
    """Extended user response for admin views with role information."""

    role: str = Field(..., description="User role (user, moderator, admin)")


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


class SystemStatsResponse(BaseModel):
    """System statistics response for admin dashboard."""

    total_users: int = Field(..., description="Total number of users")
    active_users: int = Field(..., description="Number of active users")
    verified_users: int = Field(..., description="Number of verified users")
    admin_users: int = Field(..., description="Number of admin users")
    moderator_users: int = Field(..., description="Number of moderator users")
