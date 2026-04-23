"""Initial schema (ported from SQL migrations 001-006)

Revision ID: 001
Revises:
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "source_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("content_hash", sa.Text, nullable=False),
        sa.Column("raw_content", sa.Text),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("url", name="uq_snapshot_url"),
    )

    op.create_table(
        "promotions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("source_program", sa.Text, nullable=False),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("promo_type", sa.Text, nullable=False, server_default="other"),
        sa.Column("origin_program", sa.Text),
        sa.Column("destination_program", sa.Text),
        sa.Column("bonus_percent", sa.Numeric(6, 2)),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("conditions", sa.Text),
        sa.Column("requires_club", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requires_card", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("cpf_limit", sa.Text),
        sa.Column(
            "confidence", sa.Numeric(3, 2), nullable=False, server_default="0.80"
        ),
        sa.Column("raw_data", postgresql.JSONB),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("fingerprint", name="uq_promotion_fingerprint"),
    )

    op.create_index("ix_promotions_promo_type", "promotions", ["promo_type"])
    op.create_index("ix_promotions_ends_at", "promotions", ["ends_at"])
    op.create_index("ix_promotions_source_program", "promotions", ["source_program"])

    op.create_table(
        "user_preferences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("monitored_programs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("transfer_pairs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("accumulation_programs", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "alert_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("digest_id", sa.Text),
        sa.UniqueConstraint("fingerprint", name="uq_alert_fingerprint"),
    )


def downgrade() -> None:
    op.drop_table("alert_history")
    op.drop_table("user_preferences")
    op.drop_index("ix_promotions_source_program", "promotions")
    op.drop_index("ix_promotions_ends_at", "promotions")
    op.drop_index("ix_promotions_promo_type", "promotions")
    op.drop_table("promotions")
    op.drop_table("source_snapshots")
