"""Create the reward_ledger points table.

Append-only ledger: every GitHub activity, learning-module completion, and
redemption (mentor session) is a row. Balance = SUM(points). The unique
constraint on (user_id, source, activity, reference_key) makes awards
idempotent — replaying a GitHub sync never double-credits.

Revision ID: 20261006_0005
Revises: 20261006_0004
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261006_0005"
down_revision: str | Sequence[str] | None = "20261006_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    context_type = sa.JSON().with_variant(JSONB(), "postgresql")

    op.create_table(
        "reward_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("activity", sa.String(length=50), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reference_key", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("metadata", context_type, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "source", "activity", "reference_key", name="uq_reward_dedupe"
        ),
    )
    op.create_index("ix_reward_ledger_user_id", "reward_ledger", ["user_id"])
    op.create_index("ix_reward_ledger_source", "reward_ledger", ["source"])
    op.create_index("ix_reward_ledger_activity", "reward_ledger", ["activity"])
    op.create_index(
        "ix_reward_ledger_user_created", "reward_ledger", ["user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_reward_ledger_user_created", table_name="reward_ledger")
    op.drop_index("ix_reward_ledger_activity", table_name="reward_ledger")
    op.drop_index("ix_reward_ledger_source", table_name="reward_ledger")
    op.drop_index("ix_reward_ledger_user_id", table_name="reward_ledger")
    op.drop_table("reward_ledger")
