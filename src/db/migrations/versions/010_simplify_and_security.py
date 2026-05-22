"""Simplify schema and enable Row Level Security.

- Drop source_snapshots table (hash_diff monitor removed)
- Enable RLS on all tables to block PostgREST anon access
- Remove duplicate promotions with no email history

Revision ID: 010
Revises: 009
"""

from __future__ import annotations

from alembic import op

revision: str = "010"
down_revision: str = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove table used exclusively by the removed hash_diff monitor
    op.execute("DROP TABLE IF EXISTS source_snapshots CASCADE")

    # Remove duplicate transfer_bonus promotions (no email sent for them)
    # Keeps the most recent entry per logical group (origin, dest, bonus, month)
    op.execute("""
        DELETE FROM promotions
        WHERE id IN (
            SELECT p.id
            FROM promotions p
            WHERE p.promo_type = 'transfer_bonus'
              AND p.ends_at IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM email_log el WHERE el.promo_id = p.id
              )
              AND EXISTS (
                  SELECT 1 FROM promotions p2
                  WHERE p2.promo_type = 'transfer_bonus'
                    AND p2.origin_program IS NOT DISTINCT FROM p.origin_program
                    AND p2.destination_program IS NOT DISTINCT FROM p.destination_program
                    AND p2.bonus_percent IS NOT DISTINCT FROM p.bonus_percent
                    AND to_char(p2.ends_at AT TIME ZONE 'UTC', 'YYYY-MM')
                        = to_char(p.ends_at AT TIME ZONE 'UTC', 'YYYY-MM')
                    AND p2.id != p.id
                    AND p2.created_at > p.created_at
              )
        )
    """)

    # Enable Row Level Security on all tables
    # Service role (used by pipeline and Vercel API via DATABASE_URL) bypasses RLS.
    # This blocks unauthenticated PostgREST (anon key) access entirely.
    for table in [
        "promotions",
        "user_preferences",
        "email_log",
        "automation_logs",
        "monitor_state",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # Deny all access to anon and authenticated roles (PostgREST)
    # Service role is exempt from RLS policies in Supabase.
    for table in [
        "promotions",
        "user_preferences",
        "email_log",
        "automation_logs",
        "monitor_state",
    ]:
        op.execute(
            f"DO $$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='{table}' AND policyname='deny_all_{table}') "
            f"THEN CREATE POLICY deny_all_{table} ON {table} FOR ALL USING (false); "
            f"END IF; END $$"
        )


def downgrade() -> None:
    for table in [
        "promotions",
        "user_preferences",
        "email_log",
        "automation_logs",
        "monitor_state",
    ]:
        op.execute(f"DROP POLICY IF EXISTS deny_all_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE TABLE IF NOT EXISTS source_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            url TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            raw_content TEXT,
            fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
