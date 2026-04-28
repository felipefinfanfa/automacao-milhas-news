"""Convert user_preferences array columns from text[] to jsonb

Revision ID: 005
Revises: 004
Create Date: 2026-04-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLS = ["monitored_programs", "transfer_pairs", "accumulation_programs"]


def _col_type(conn: sa.engine.Connection, col: str) -> str:
    row = conn.execute(
        sa.text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_name='user_preferences' AND column_name=:col"
        ),
        {"col": col},
    ).fetchone()
    return row[0] if row else ""


def upgrade() -> None:
    conn = op.get_bind()
    for col in COLS:
        dtype = _col_type(conn, col)
        if dtype and dtype != "jsonb":
            op.execute(sa.text(f"ALTER TABLE user_preferences ALTER COLUMN {col} DROP DEFAULT"))
            op.execute(
                sa.text(
                    f"ALTER TABLE user_preferences "
                    f"ALTER COLUMN {col} TYPE jsonb USING to_jsonb({col})"
                )
            )
            op.execute(
                sa.text(
                    f"ALTER TABLE user_preferences " f"ALTER COLUMN {col} SET DEFAULT '[]'::jsonb"
                )
            )


def downgrade() -> None:
    pass
