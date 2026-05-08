"""Add automation_logs table

Revision ID: 008
Revises: 007
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("workflow", sa.Text, nullable=False),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("signals_found", sa.Integer, server_default="0"),
        sa.Column("promos_new", sa.Integer, server_default="0"),
        sa.Column("emails_sent", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("error_traceback", sa.Text),
        sa.Column("duration_seconds", sa.Numeric(8, 2)),
        sa.Column("gh_run_id", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("automation_logs")
