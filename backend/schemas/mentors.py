"""Typed API contracts for the mentors catalog used by the Redeem module."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MentorItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Mentor identifier.")
    name: str = Field(description="Mentor display name.")
    role: str = Field(description="Current role/title.")
    company: str = Field(description="Company or project affiliation.")
    tier: str = Field(description="Pricing tier: beginner | intermediate | advanced | expert.")
    cost: int = Field(description="Points required to redeem a session.")
    rating: float = Field(description="Average session rating.")
    sessions: int = Field(description="Number of sessions delivered.")
    languages: list[str] = Field(description="Languages the mentor works in.")
    timezone: str = Field(description="Mentor timezone label.")
    tags: list[str] = Field(description="Topics the mentor can help with.")
    bio: str = Field(description="Short mentor bio.")


class MentorListResponse(BaseModel):
    mentors: list[MentorItem] = Field(description="Active mentor catalog.")
    total: int = Field(default=0, description="Number of mentors returned.")
    tiers: dict[str, int] = Field(
        default_factory=dict, description="Tier -> points cost, ordered beginner to expert."
    )
