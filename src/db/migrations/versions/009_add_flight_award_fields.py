"""Add flight_award fields to promotions and user_preferences

Revision ID: 009
Revises: 008
Create Date: 2026-05-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("origin_iata", sa.Text(), nullable=True))
    op.add_column("promotions", sa.Column("destination_iata", sa.Text(), nullable=True))
    op.add_column("promotions", sa.Column("miles_count", sa.Integer(), nullable=True))
    op.add_column(
        "user_preferences",
        sa.Column(
            "flight_routes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "flight_programs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "flight_programs")
    op.drop_column("user_preferences", "flight_routes")
    op.drop_column("promotions", "miles_count")
    op.drop_column("promotions", "destination_iata")
    op.drop_column("promotions", "origin_iata")
