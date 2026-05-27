"""Enforce max 40 users via trigger on user_preferences.

Adds a BEFORE INSERT trigger that rejects new rows when the
user count already reaches 40.

Revision ID: 012
Revises: 011
"""

from __future__ import annotations

from alembic import op

revision: str = "012"
down_revision: str = "011"
branch_labels = None
depends_on = None

_MAX_USERS = 40


def upgrade() -> None:
    op.execute(f"""
        CREATE OR REPLACE FUNCTION enforce_max_users()
        RETURNS TRIGGER AS $$
        BEGIN
            IF (SELECT COUNT(*) FROM user_preferences) >= {_MAX_USERS} THEN
                RAISE EXCEPTION 'Limite de vagas atingido (máximo: {_MAX_USERS})';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_enforce_max_users
            BEFORE INSERT ON user_preferences
            FOR EACH ROW
            EXECUTE FUNCTION enforce_max_users();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_max_users ON user_preferences")
    op.execute("DROP FUNCTION IF EXISTS enforce_max_users()")
