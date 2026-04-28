"""Add missing created_at/updated_at to user_preferences if not present

Revision ID: 004
Revises: 003
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    has_created = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user_preferences' AND column_name='created_at'"
        )
    ).fetchone()

    if not has_created:
        op.add_column(
            "user_preferences",
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    has_updated = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user_preferences' AND column_name='updated_at'"
        )
    ).fetchone()

    if not has_updated:
        op.add_column(
            "user_preferences",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    pass
