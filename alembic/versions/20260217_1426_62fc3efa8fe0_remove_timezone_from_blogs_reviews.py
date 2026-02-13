"""
Remove timezone from blogs and reviews tables.

Revision ID: 62fc3efa8fe0
Revises: aa3094bd711d
Create Date: 2026-02-17 14:26:47.351727

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Revision identifiers, used by Alembic
revision: str = "62fc3efa8fe0"
down_revision: str | Sequence[str] | None = "aa3094bd711d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply schema changes for this revision."""
    op.drop_column("blogs", "timezone")
    op.drop_column("reviews", "timezone")


def downgrade() -> None:
    """Revert schema changes for this revision."""
    op.add_column(
        "reviews",
        sa.Column("timezone", sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    )
    op.add_column(
        "blogs",
        sa.Column("timezone", sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    )
