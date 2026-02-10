"""
Blog content varchar to text.

Revision ID: 7f50ddc7ccb6
Revises: 29cb6c6a497a
Create Date: 2026-02-10 18:12:23.387666

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Revision identifiers, used by Alembic
revision: str = "7f50ddc7ccb6"
down_revision: str | Sequence[str] | None = "29cb6c6a497a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply schema changes for this revision."""
    # Change blogs.content from VARCHAR(50000) to TEXT for better long content handling
    op.alter_column(
        "blogs",
        "content",
        existing_type=sa.VARCHAR(length=50000),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert schema changes for this revision."""
    # Revert blogs.content back to VARCHAR(50000)
    op.alter_column(
        "blogs",
        "content",
        existing_type=sa.Text(),
        type_=sa.VARCHAR(length=50000),
        existing_nullable=False,
    )
