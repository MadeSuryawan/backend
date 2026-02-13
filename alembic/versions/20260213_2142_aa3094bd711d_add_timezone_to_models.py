"""
Add timezone column to users, blogs, and reviews tables.

Revision ID: aa3094bd711d
Revises: 20260211_1711
Create Date: 2026-02-13 21:42:17.676163

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Revision identifiers, used by Alembic
revision: str = "aa3094bd711d"
down_revision: str | Sequence[str] | None = "20260211_1711"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add timezone column to users, blogs, and reviews tables."""
    # Add timezone column to users table
    op.add_column("users", sa.Column("timezone", sa.String(length=50), nullable=True))

    # Add timezone column to blogs table
    op.add_column("blogs", sa.Column("timezone", sa.String(length=50), nullable=True))

    # Add timezone column to reviews table
    op.add_column("reviews", sa.Column("timezone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Remove timezone column from users, blogs, and reviews tables."""
    # Drop timezone column from reviews table
    op.drop_column("reviews", "timezone")

    # Drop timezone column from blogs table
    op.drop_column("blogs", "timezone")

    # Drop timezone column from users table
    op.drop_column("users", "timezone")
