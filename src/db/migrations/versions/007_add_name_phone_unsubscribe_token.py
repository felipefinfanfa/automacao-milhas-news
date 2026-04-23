"""Add name, phone, unsubscribe_token to user_preferences

Revision ID: 007
Revises: 006
Create Date: 2026-04-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _col_exists(conn: sa.engine.Connection, column: str) -> bool:
    return conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user_preferences' AND column_name=:col"
        ),
        {"col": column},
    ).fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()

    if not _col_exists(conn, "name"):
        op.add_column("user_preferences", sa.Column("name", sa.Text, nullable=True))

    if not _col_exists(conn, "phone"):
        op.add_column("user_preferences", sa.Column("phone", sa.Text, nullable=True))

    if not _col_exists(conn, "unsubscribe_token"):
        op.add_column(
            "user_preferences",
            sa.Column(
                "unsubscribe_token",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
        )
        op.execute(
            sa.text(
                "UPDATE user_preferences "
                "SET unsubscribe_token = gen_random_uuid() "
                "WHERE unsubscribe_token IS NULL"
            )
        )
        op.alter_column("user_preferences", "unsubscribe_token", nullable=False)
        op.create_unique_constraint(
            "uq_user_preferences_unsubscribe_token",
            "user_preferences",
            ["unsubscribe_token"],
        )
        op.create_index(
            "ix_user_preferences_unsubscribe_token",
            "user_preferences",
            ["unsubscribe_token"],
        )


def downgrade() -> None:
    conn = op.get_bind()

    if _col_exists(conn, "unsubscribe_token"):
        op.drop_index("ix_user_preferences_unsubscribe_token", "user_preferences")
        op.drop_constraint(
            "uq_user_preferences_unsubscribe_token", "user_preferences", type_="unique"
        )
        op.drop_column("user_preferences", "unsubscribe_token")

    if _col_exists(conn, "phone"):
        op.drop_column("user_preferences", "phone")

    if _col_exists(conn, "name"):
        op.drop_column("user_preferences", "name")
