"""RewardLedger ORM model — an append-only points ledger for user activities.

Every earn (GitHub activity, learning module completion) and every redemption
(mentor session) is a row here. ``points`` is positive for earnings and
negative for redemptions; the balance is simply ``SUM(points)``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class RewardLedger(Base):
    __tablename__ = "reward_ledger"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "activity", "reference_key", name="uq_reward_dedupe"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    activity: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    # Idempotency key: GitHub event id + commit sha, tutorial/roadmap/step ids,
    # or the redemption booking reference. Awards with the same key are ignored.
    reference_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
