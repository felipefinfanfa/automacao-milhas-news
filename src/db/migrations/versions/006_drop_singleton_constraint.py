"""Remove singleton unique constraint from user_preferences

The table was originally created as a single-row store. Remove the
uq_user_preferences_singleton constraint to allow one row per user.

Revision ID: 006
Revises: 005
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    row = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name='user_preferences' "
            "AND constraint_name='uq_user_preferences_singleton'"
        )
    ).fetchone()
    if row:
        op.drop_constraint(
            "uq_user_preferences_singleton", "user_preferences", type_="unique"
        )


def downgrade() -> None:
    pass
