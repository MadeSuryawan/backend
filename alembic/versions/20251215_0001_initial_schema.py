"""
Initial schema: Create users and blogs tables.

Revision ID: 0001
Revises:
Create Date: 2025-12-15

This migration creates the complete initial schema for the BaliBlissed application:
- users: User accounts with authentication and profile information
- blogs: Blog posts with author relationship and metadata
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# Revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply schema changes for this revision."""
    # Create users table
    op.create_table(
        "users",
        sa.Column("uuid", sa.UUID(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("auth_provider", sa.String(length=50), server_default="email", nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("bio", sa.String(length=160), nullable=True),
        sa.Column("profile_picture", sa.String(length=500), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("date_of_birth", sa.String(length=10), nullable=True),
        sa.Column("gender", sa.String(length=50), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("role", sa.String(length=20), server_default="user", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    # Create indexes for users table
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_provider_id", "users", ["provider_id"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    # Create blogs table
    op.create_table(
        "blogs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("content", sa.String(length=50000), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reading_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("images_url", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.uuid"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    # Create indexes for blogs table
    op.create_index("ix_blogs_slug", "blogs", ["slug"], unique=True)
    op.create_index("ix_blogs_author_id", "blogs", ["author_id"], unique=False)
    op.create_index("ix_blogs_status", "blogs", ["status"], unique=False)
    op.create_index("ix_blogs_created_at", "blogs", ["created_at"], unique=False)
    # Composite indexes
    op.create_index("ix_blogs_status_created", "blogs", ["status", "created_at"], unique=False)
    op.create_index("ix_blogs_author_status", "blogs", ["author_id", "status"], unique=False)
    # GIN index for JSONB tags column
    op.create_index(
        "ix_blogs_tags_gin",
        "blogs",
        ["tags"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    """Revert schema changes for this revision."""
    # Drop blogs table and its indexes
    op.drop_index("ix_blogs_tags_gin", table_name="blogs")
    op.drop_index("ix_blogs_author_status", table_name="blogs")
    op.drop_index("ix_blogs_status_created", table_name="blogs")
    op.drop_index("ix_blogs_created_at", table_name="blogs")
    op.drop_index("ix_blogs_status", table_name="blogs")
    op.drop_index("ix_blogs_author_id", table_name="blogs")
    op.drop_index("ix_blogs_slug", table_name="blogs")
    op.drop_table("blogs")

    # Drop users table and its indexes
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_provider_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
