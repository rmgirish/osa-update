"""Mentor catalog service — the backend source of truth for the Redeem module.

The catalog is seeded once from a curated default list, so the frontend no longer
hardcodes mentors. ``list_mentors`` lazily seeds on first read when the table is
empty, which keeps fresh test databases working without a manual step.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.mentor_model import Mentor

TIER_ORDER = ("beginner", "intermediate", "advanced", "expert")

# Curated default catalog (also used to seed the table).
DEFAULT_MENTORS: list[dict[str, object]] = [
    {
        "name": "Aarav Mehta",
        "role": "Senior Backend Engineer",
        "company": "Zerodha",
        "tier": "beginner",
        "cost": 100,
        "rating": 4.9,
        "sessions": 128,
        "languages": ["Python", "Go"],
        "timezone": "IST (UTC+5:30)",
        "tags": ["First PR", "Git Basics", "Setup Help"],
        "bio": "Guided 100+ first-time contributors through their first merged pull request.",
    },
    {
        "name": "Sofia Ramirez",
        "role": "Open Source Maintainer",
        "company": "Expo",
        "tier": "intermediate",
        "cost": 300,
        "rating": 4.8,
        "sessions": 86,
        "languages": ["TypeScript", "React"],
        "timezone": "CET (UTC+1)",
        "tags": ["Code Review", "CI/CD", "React"],
        "bio": "Maintains popular React Native tooling; loves unblocking stuck contributors.",
    },
    {
        "name": "Kenji Tanaka",
        "role": "Staff Engineer",
        "company": "Rust Foundation",
        "tier": "advanced",
        "cost": 600,
        "rating": 4.9,
        "sessions": 54,
        "languages": ["Rust", "C++"],
        "timezone": "JST (UTC+9)",
        "tags": ["Performance", "Systems", "Testing"],
        "bio": "Performance specialist; can profile and untangle gnarly systems code with you.",
    },
    {
        "name": "Dr. Amara Okafor",
        "role": "Principal Engineer",
        "company": "Moorhen Health",
        "tier": "expert",
        "cost": 1000,
        "rating": 5.0,
        "sessions": 31,
        "languages": ["Python", "TypeScript"],
        "timezone": "GMT (UTC+0)",
        "tags": ["Career", "Leadership", "Architecture"],
        "bio": "20 years in open source; mentors future maintainers and OSS program leads.",
    },
    {
        "name": "Priya Sharma",
        "role": "DevOps Engineer",
        "company": "Razorpay",
        "tier": "beginner",
        "cost": 100,
        "rating": 4.7,
        "sessions": 97,
        "languages": ["Python", "Docker"],
        "timezone": "IST (UTC+5:30)",
        "tags": ["Docker", "First PR", "Linux"],
        "bio": "Patient teacher for dev environments, containers and contributor workflows.",
    },
    {
        "name": "Lucas Weber",
        "role": "Core Maintainer",
        "company": "Vite Team",
        "tier": "intermediate",
        "cost": 300,
        "rating": 4.8,
        "sessions": 73,
        "languages": ["JavaScript", "Rust"],
        "timezone": "GMT+2",
        "tags": ["Build Tools", "Testing", "Plugin APIs"],
        "bio": "Reviews contributor PRs weekly; great for understanding maintainer expectations.",
    },
]


async def ensure_seed(db: AsyncSession) -> None:
    """Insert the default catalog once when the mentors table is empty."""
    existing = await db.scalar(select(func.count(Mentor.id)))
    if int(existing or 0) > 0:
        return
    db.add_all([Mentor(**data) for data in DEFAULT_MENTORS])
    await db.commit()


def tier_costs(mentors: list[Mentor]) -> dict[str, int]:
    """Return tier -> points cost, ordered beginner to expert."""
    costs: dict[str, int] = {}
    for mentor in mentors:
        current = costs.get(mentor.tier)
        if current is None or mentor.cost < current:
            costs[mentor.tier] = mentor.cost
    return {tier: costs[tier] for tier in TIER_ORDER if tier in costs}


async def list_mentors(db: AsyncSession, tag: str | None = None) -> list[Mentor]:
    """List active mentors, optionally filtered by a topic tag."""
    await ensure_seed(db)
    result = await db.scalars(
        select(Mentor).where(Mentor.is_active.is_(True)).order_by(Mentor.cost.asc(), Mentor.id.asc())
    )
    mentors = list(result.all())
    if tag and tag.strip():
        wanted = tag.strip().lower()
        mentors = [m for m in mentors if wanted in {t.lower() for t in (m.tags or [])}]
    return mentors


async def get_mentor(db: AsyncSession, mentor_id: int) -> Mentor | None:
    """Fetch a single active mentor by id."""
    await ensure_seed(db)
    return await db.scalar(
        select(Mentor).where(Mentor.id == mentor_id, Mentor.is_active.is_(True))
    )
