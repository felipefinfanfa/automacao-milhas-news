"""Add email_log, monitor_state; add user_id to user_preferences

Revision ID: 002
Revises: 001
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_unique_constraint("uq_user_preferences_user_id", "user_preferences", ["user_id"])

    op.create_table(
        "email_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "promo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("promotions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day_number", sa.Integer, nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "promo_id", "day_number", name="uq_email_log"),
    )
    op.create_index("ix_email_log_user_id", "email_log", ["user_id"])
    op.create_index("ix_email_log_promo_id", "email_log", ["promo_id"])

    op.create_table(
        "monitor_state",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("domain", sa.Text, nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("domain", name="uq_monitor_state_domain"),
    )


def downgrade() -> None:
    op.drop_table("monitor_state")
    op.drop_index("ix_email_log_promo_id", "email_log")
    op.drop_index("ix_email_log_user_id", "email_log")
    op.drop_table("email_log")
    op.drop_constraint("uq_user_preferences_user_id", "user_preferences", type_="unique")
    op.drop_column("user_preferences", "user_id")
