"""profile fields and analyses

Revision ID: 7c3d1a9e5b20
Revises: f0a5eec0e1b4
Create Date: 2026-09-25 13:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c3d1a9e5b20"
down_revision: str | None = "f0a5eec0e1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("users", sa.Column("designation", sa.String(length=200), nullable=True))
    op.create_table(
        "analyses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("variant", sa.String(length=20), nullable=True),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("frames", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_analyses_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analyses"),
    )
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"])
    op.create_index("ix_analyses_created_at", "analyses", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_analyses_created_at", table_name="analyses")
    op.drop_index("ix_analyses_user_id", table_name="analyses")
    op.drop_table("analyses")
    op.drop_column("users", "designation")
    op.drop_column("users", "state")
