"""Pydantic schemas for the rewards system."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RewardEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    activity: str
    points: int
    reference_key: str | None
    description: str | None
    extra_metadata: dict[str, Any] | None = Field(default=None, alias="extra_metadata")
    occurred_at: datetime | None
    created_at: datetime


class RewardsSummary(BaseModel):
    """Balance snapshot plus the active points rules for the UI."""

    balance: int
    breakdown: dict[str, int]
    rules: dict[str, dict[str, int]]
    recent: list[RewardEntry]


class LedgerResponse(BaseModel):
    items: list[RewardEntry]
    total: int
    limit: int
    offset: int


class GithubSyncResponse(BaseModel):
    balance: int
    total_awarded: int
    events_scanned: int
    awarded: list[RewardEntry]


class TutorialAwardRequest(BaseModel):
    tutorial_id: str = Field(min_length=1, max_length=100)
    tutorial_title: str | None = Field(default=None, max_length=255)


class TutorialAwardResponse(BaseModel):
    awarded: bool
    points: int
    balance: int


class RedeemRequest(BaseModel):
    amount: int = Field(gt=0, description="Points to spend (positive number).")
    mentor_id: int | None = None
    mentor_name: str | None = Field(default=None, max_length=255)
    tier: str | None = Field(default=None, max_length=50)
    date: str | None = Field(default=None, max_length=30)
    time: str | None = Field(default=None, max_length=30)
    topic: str | None = Field(default=None, max_length=500)


class RedeemResponse(BaseModel):
    balance: int
    redemption: RewardEntry


class CancelRedemptionRequest(BaseModel):
    reference_key: str = Field(min_length=1, max_length=255)


class CancelRedemptionResponse(BaseModel):
    refunded: bool
    balance: int


class ClaimState(BaseModel):
    """A claimable points reward and whether it can be claimed right now."""

    id: str
    label: str
    points: int
    available: bool
    next_available_at: datetime | None = Field(
        default=None, description="When the claim resets, if it is currently on cooldown."
    )


class ClaimsResponse(BaseModel):
    claims: list[ClaimState]


class ClaimResult(BaseModel):
    awarded: bool
    points: int
    balance: int
    next_available_at: datetime | None = None
