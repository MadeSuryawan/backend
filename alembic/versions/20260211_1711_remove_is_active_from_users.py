"""
Remove is_active column from users table.

Revision ID: 20260211_1711
Revises: 20260210_1812
Create Date: 2026-02-11

This migration removes the is_active column from the users table
as it's no longer needed for user status management.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Revision identifiers, used by Alembic
revision: str = "20260211_1711"
down_revision: str = "7f50ddc7ccb6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - remove is_active column from users table."""
    op.drop_column("users", "is_active")


def downgrade() -> None:
    """Revert migration - add back is_active column."""
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
