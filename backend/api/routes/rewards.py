"""Routes for the rewards system: balances, GitHub sync, learning awards, redemptions."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_current_user
from backend.core.database import get_db
from backend.schemas.rewards import (
    CancelRedemptionRequest,
    CancelRedemptionResponse,
    ClaimResult,
    ClaimsResponse,
    ClaimState,
    GithubSyncResponse,
    LedgerResponse,
    RedeemRequest,
    RedeemResponse,
    RewardEntry,
    RewardsSummary,
    TutorialAwardRequest,
    TutorialAwardResponse,
)
from backend.services import rewards_service
from backend.services.github_client import GitHubAPIError

router = APIRouter(prefix="/rewards", tags=["Rewards"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[dict[str, Any], Depends(get_current_user)]


def _user_id(user: dict[str, Any]) -> uuid.UUID:
    return uuid.UUID(user["user_id"])


# ── Balance & ledger ──


@router.get(
    "/me",
    response_model=RewardsSummary,
    status_code=status.HTTP_200_OK,
    summary="Get my points balance, breakdown, rules, and recent activity",
)
async def get_my_rewards(session: DbSession, user: CurrentUser) -> RewardsSummary:
    user_id = _user_id(user)
    balance = await rewards_service.get_balance(session, user_id)
    breakdown = await rewards_service.get_breakdown(session, user_id)
    recent, _ = await rewards_service.get_ledger(session, user_id, limit=10)
    return RewardsSummary(
        balance=balance,
        breakdown=breakdown,
        rules=rewards_service.POINTS_RULES,
        recent=[RewardEntry.model_validate(entry) for entry in recent],
    )


@router.get(
    "/ledger",
    response_model=LedgerResponse,
    status_code=status.HTTP_200_OK,
    summary="Get my paginated points ledger",
)
async def get_my_ledger(
    session: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LedgerResponse:
    items, total = await rewards_service.get_ledger(session, _user_id(user), limit, offset)
    return LedgerResponse(
        items=[RewardEntry.model_validate(entry) for entry in items],
        total=total,
        limit=limit,
        offset=offset,
    )


# ── GitHub activity points ──


@router.post(
    "/sync-github",
    response_model=GithubSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Award points for my recent GitHub activity",
    description=(
        "Replays recent public GitHub events (commits, pull requests, issues, reviews, "
        "stars, forks) into the points ledger. Idempotent: each GitHub event is credited "
        "once, so repeated syncs only award genuinely new activity."
    ),
)
async def sync_github_rewards(session: DbSession, user: CurrentUser) -> GithubSyncResponse:
    github_username = user.get("github_username")
    if not github_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Link a GitHub account first (GitHub OAuth or PAT login).",
        )
    try:
        result = await rewards_service.sync_github_rewards(
            session,
            _user_id(user),
            github_username,
            token=user.get("github_access_token"),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"GitHub access is not configured: {exc}",
        ) from exc
    except GitHubAPIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    balance = await rewards_service.get_balance(session, _user_id(user))
    return GithubSyncResponse(
        balance=balance,
        total_awarded=result["total_awarded"],
        events_scanned=result["events_scanned"],
        awarded=[RewardEntry.model_validate(entry) for entry in result["awarded"]],
    )


# ── Claimable points (manual daily check-in) ──


@router.get(
    "/claims",
    response_model=ClaimsResponse,
    status_code=status.HTTP_200_OK,
    summary="List claimable point rewards for the signed-in user",
)
async def list_claims(session: DbSession, user: CurrentUser) -> ClaimsResponse:
    """Return which manual claims are available (and when they reset)."""
    status_payload = await rewards_service.get_claim_status(session, _user_id(user))
    return ClaimsResponse(claims=[ClaimState(**status_payload)])


@router.post(
    "/claims/daily",
    response_model=ClaimResult,
    status_code=status.HTTP_200_OK,
    summary="Claim the daily check-in points",
    description=(
        "Credits the daily check-in award once per UTC day. Re-claiming the same "
        "day reports awarded=false and returns the unchanged balance."
    ),
)
async def claim_daily(session: DbSession, user: CurrentUser) -> ClaimResult:
    user_id = _user_id(user)
    entry, next_available_at = await rewards_service.claim_daily(session, user_id)
    balance = await rewards_service.get_balance(session, user_id)
    return ClaimResult(
        awarded=entry is not None,
        points=entry.points if entry is not None else 0,
        balance=balance,
        next_available_at=next_available_at,
    )


# ── Learning-module points ──


@router.post(
    "/tutorial-completed",
    response_model=TutorialAwardResponse,
    status_code=status.HTTP_200_OK,
    summary="Award points for completing a learning tutorial",
    description=(
        "Credits the fixed tutorial-completion award (see rules). Idempotent per "
        "tutorial, so repeated calls for the same tutorial never double-credit."
    ),
)
async def award_tutorial(
    session: DbSession,
    user: CurrentUser,
    payload: TutorialAwardRequest,
) -> TutorialAwardResponse:
    entry = await rewards_service.award_tutorial_completed(
        session, _user_id(user), payload.tutorial_id, payload.tutorial_title
    )
    balance = await rewards_service.get_balance(session, _user_id(user))
    return TutorialAwardResponse(
        awarded=entry is not None,
        points=entry.points if entry is not None else 0,
        balance=balance,
    )


# ── Redemptions (spend points) ──


@router.post(
    "/redeem",
    response_model=RedeemResponse,
    status_code=status.HTTP_200_OK,
    summary="Redeem points for a 1:1 mentor session",
)
async def redeem_points(
    session: DbSession,
    user: CurrentUser,
    payload: RedeemRequest,
) -> RedeemResponse:
    description_parts = [
        f"Mentor session with {payload.mentor_name or 'mentor'}"
        f" ({payload.tier or 'standard tier'})"
    ]
    if payload.date or payload.time:
        description_parts.append(f"on {payload.date or 'TBD'} at {payload.time or 'TBD'}")
    if payload.topic:
        description_parts.append(f"— {payload.topic}")

    try:
        redemption = await rewards_service.redeem(
            session,
            _user_id(user),
            payload.amount,
            description=", ".join(description_parts),
            extra_metadata={
                "mentor_id": payload.mentor_id,
                "mentor_name": payload.mentor_name,
                "tier": payload.tier,
                "date": payload.date,
                "time": payload.time,
                "topic": payload.topic,
            },
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    balance = await rewards_service.get_balance(session, _user_id(user))
    return RedeemResponse(
        balance=balance,
        redemption=RewardEntry.model_validate(redemption),
    )


@router.post(
    "/redemptions/cancel",
    response_model=CancelRedemptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a redemption and refund its points",
)
async def cancel_redemption(
    session: DbSession,
    user: CurrentUser,
    payload: CancelRedemptionRequest,
) -> CancelRedemptionResponse:
    refunded = await rewards_service.cancel_redemption(
        session, _user_id(user), payload.reference_key
    )
    balance = await rewards_service.get_balance(session, _user_id(user))
    return CancelRedemptionResponse(refunded=refunded, balance=balance)
