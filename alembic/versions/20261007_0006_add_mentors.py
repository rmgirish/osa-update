"""Create the mentors catalog table.

Backs the Redeem module: the mentor catalog is now served by the backend and
seeded from a curated default list instead of being hardcoded in the frontend.

Revision ID: 20261007_0006
Revises: 20261006_0005
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20261007_0006"
down_revision: str | Sequence[str] | None = "20261006_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    context_type = sa.JSON().with_variant(JSONB(), "postgresql")

    op.create_table(
        "mentors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("company", sa.String(length=120), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False),
        sa.Column("cost", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("languages", context_type, nullable=False),
        sa.Column("timezone", sa.String(length=60), nullable=False),
        sa.Column("tags", context_type, nullable=False),
        sa.Column("bio", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mentors_tier", "mentors", ["tier"])


def downgrade() -> None:
    op.drop_index("ix_mentors_tier", table_name="mentors")
    op.drop_table("mentors")
