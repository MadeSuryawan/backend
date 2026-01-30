"""
Add reviews table and blog videos_url column.

Revision ID: add_reviews_blog_videos
Revises: 5f3ec632a8e7
Create Date: 2026-01-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "add_reviews_blog_videos"
down_revision: str | Sequence[str] | None = "5f3ec632a8e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add reviews table and videos_url to blogs."""
    # Add videos_url column to blogs table
    op.add_column(
        "blogs",
        sa.Column("videos_url", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # Create reviews table
    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("item_id", sa.UUID(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("content", sa.String(length=2000), nullable=False),
        sa.Column("images_url", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "is_verified_purchase",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "helpful_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.uuid"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for reviews table
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"], unique=False)
    op.create_index("ix_reviews_item_id", "reviews", ["item_id"], unique=False)
    op.create_index("ix_reviews_user_item", "reviews", ["user_id", "item_id"], unique=False)
    op.create_index("ix_reviews_rating", "reviews", ["rating"], unique=False)
    op.create_index("ix_reviews_created_at", "reviews", ["created_at"], unique=False)


def downgrade() -> None:
    """Remove reviews table and videos_url from blogs."""
    # Drop indexes
    op.drop_index("ix_reviews_created_at", table_name="reviews")
    op.drop_index("ix_reviews_rating", table_name="reviews")
    op.drop_index("ix_reviews_user_item", table_name="reviews")
    op.drop_index("ix_reviews_item_id", table_name="reviews")
    op.drop_index("ix_reviews_user_id", table_name="reviews")

    # Drop reviews table
    op.drop_table("reviews")

    # Drop videos_url column from blogs
    op.drop_column("blogs", "videos_url")

