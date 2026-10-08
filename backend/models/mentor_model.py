"""Mentor ORM model — the redeemable 1:1 mentor catalog.

Mentors are seeded from a curated default list; the redeem flow prices a session
from ``cost`` and stores the booking details on the rewards ledger.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class Mentor(Base):
    __tablename__ = "mentors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False)
    company: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="beginner", index=True)
    cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    languages: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    timezone: Mapped[str] = mapped_column(String(60), nullable=False, default="UTC")
    tags: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list
    )
    bio: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
