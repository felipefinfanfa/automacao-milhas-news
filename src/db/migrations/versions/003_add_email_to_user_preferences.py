"""Add email column to user_preferences

Revision ID: 003
Revises: 002
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("email", sa.Text, nullable=True),
    )
    op.create_unique_constraint("uq_user_preferences_email", "user_preferences", ["email"])
    op.create_index("ix_user_preferences_email", "user_preferences", ["email"])


def downgrade() -> None:
    op.drop_index("ix_user_preferences_email", "user_preferences")
    op.drop_constraint("uq_user_preferences_email", "user_preferences", type_="unique")
    op.drop_column("user_preferences", "email")
