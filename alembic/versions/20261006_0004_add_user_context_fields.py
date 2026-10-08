"""Add GitHub linkage and synthesized-context columns to users.

These columns were previously only created by the runtime ``init_db`` helper
for PostgreSQL; they now live in versioned migrations so every environment
( Postgres, SQLite, CI ) converges on the same schema.

Revision ID: 20261006_0004
Revises: 20260929_0003
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261006_0004"
down_revision: str | Sequence[str] | None = "20260929_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    context_type = sa.JSON().with_variant(JSONB(), "postgresql")

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("github_username", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("github_access_token", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("user_context", sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column("skill_level", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("context", context_type, nullable=True))
        batch_op.create_index("ix_users_github_username", ["github_username"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_github_username")
        batch_op.drop_column("context")
        batch_op.drop_column("skill_level")
        batch_op.drop_column("user_context")
        batch_op.drop_column("github_access_token")
        batch_op.drop_column("github_username")
