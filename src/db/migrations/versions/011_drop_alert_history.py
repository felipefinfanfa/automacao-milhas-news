"""Drop legacy alert_history table.

Legado do sistema de digest baseado em fingerprint (anterior ao email_log
por usuário). Sem ORM model nem referências no código desde a migração 010.

Revision ID: 011
Revises: 010
"""

from __future__ import annotations

from alembic import op

revision: str = "011"
down_revision: str = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_history CASCADE")


def downgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fingerprint TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id UUID,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            digest_id UUID
        )
    """)
