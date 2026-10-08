"""Create persistent event and forum tables."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260929_0003"
down_revision: str | Sequence[str] | None = "20260928_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False, server_default="Untitled Event"),
        sa.Column("company_organization", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.Time(), nullable=False),
        sa.Column("application_url", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_name", "events", ["name"], unique=False)
    op.create_index("ix_events_company_organization", "events", ["company_organization"], unique=False)
    op.create_index("ix_events_event_type", "events", ["event_type"], unique=False)
    op.create_index("ix_events_mode", "events", ["mode"], unique=False)
    op.create_index("ix_events_event_date", "events", ["event_date"], unique=False)
    op.create_table(
        "forum_threads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forum_threads_author_id", "forum_threads", ["author_id"], unique=False)
    op.create_table(
        "forum_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["forum_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forum_posts_thread_id", "forum_posts", ["thread_id"], unique=False)
    op.create_index("ix_forum_posts_author_id", "forum_posts", ["author_id"], unique=False)
    op.create_table(
        "forum_bans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_forum_bans_user_id"),
    )
    op.create_index("ix_forum_bans_user_id", "forum_bans", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_forum_bans_user_id", table_name="forum_bans")
    op.drop_table("forum_bans")
    op.drop_index("ix_forum_posts_author_id", table_name="forum_posts")
    op.drop_index("ix_forum_posts_thread_id", table_name="forum_posts")
    op.drop_table("forum_posts")
    op.drop_index("ix_forum_threads_author_id", table_name="forum_threads")
    op.drop_table("forum_threads")
    op.drop_index("ix_events_event_date", table_name="events")
    op.drop_index("ix_events_mode", table_name="events")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_events_company_organization", table_name="events")
    op.drop_index("ix_events_name", table_name="events")
    op.drop_table("events")