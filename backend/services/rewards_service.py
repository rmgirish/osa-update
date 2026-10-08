"""Rewards engine.

Awards points for GitHub activities and learning-module completions, and
handles redemptions (mentor sessions). Every award is idempotent via the
``(user_id, source, activity, reference_key)`` unique constraint, so replaying
a GitHub sync or re-completing a module never double-credits a user.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.reward_model import RewardLedger
from backend.models.roadmap_step import RoadmapStep
from backend.models.user_roadmap_progress import UserRoadmapProgress
from backend.services.github_client import GitHubClient

logger = logging.getLogger(__name__)

# ── Points rules (single source of truth surfaced through GET /rewards/me) ──

POINTS_RULES: dict[str, dict[str, int]] = {
    "github": {
        "commit": 5,
        "pull_request": 25,
        "pull_request_merged": 50,
        "issue_opened": 10,
        "code_review": 15,
        "starred_repo": 2,
        "forked_repo": 5,
    },
    "learning": {
        "tutorial_completed": 20,
        "module_completed": 30,
        "roadmap_completed": 100,
    },
    "forum": {
        "thread_created": 15,
        "reply_posted": 5,
        "answer_accepted": 25,
        "upvote_received": 2,
    },
    "daily": {
        "login_claim": 25,
    },
}

_MAX_LEDGER_DESCRIPTION = 500


def _clip(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:_MAX_LEDGER_DESCRIPTION]


async def award(
    session: AsyncSession,
    user_id: uuid.UUID,
    source: str,
    activity: str,
    points: int,
    reference_key: str | None = None,
    description: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> RewardLedger | None:
    """Credit points once per unique reference. Returns the new row, or None
    when this activity was already awarded (idempotent replay)."""
    if reference_key is not None:
        existing = await session.scalar(
            select(RewardLedger).where(
                RewardLedger.user_id == user_id,
                RewardLedger.source == source,
                RewardLedger.activity == activity,
                RewardLedger.reference_key == reference_key,
            )
        )
        if existing is not None:
            return None

    entry = RewardLedger(
        user_id=user_id,
        source=source,
        activity=activity,
        points=points,
        reference_key=reference_key,
        description=_clip(description),
        extra_metadata=extra_metadata,
        occurred_at=occurred_at,
    )
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent request inserted the same reference first.
        await session.rollback()
        return None
    await session.refresh(entry)
    return entry


# ── Balance & ledger ──


async def get_balance(session: AsyncSession, user_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.coalesce(func.sum(RewardLedger.points), 0)).where(
            RewardLedger.user_id == user_id
        )
    )
    return int(total or 0)


async def get_breakdown(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    rows = await session.execute(
        select(RewardLedger.source, func.coalesce(func.sum(RewardLedger.points), 0))
        .where(RewardLedger.user_id == user_id)
        .group_by(RewardLedger.source)
    )
    return {source: int(total) for source, total in rows.all()}


async def get_ledger(
    session: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RewardLedger], int]:
    total = await session.scalar(
        select(func.count(RewardLedger.id)).where(RewardLedger.user_id == user_id)
    )
    result = await session.execute(
        select(RewardLedger)
        .where(RewardLedger.user_id == user_id)
        .order_by(RewardLedger.created_at.desc(), RewardLedger.id.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 200))
    )
    return list(result.scalars().all()), int(total or 0)


# ── Learning-module awards ──


async def award_tutorial_completed(
    session: AsyncSession,
    user_id: uuid.UUID,
    tutorial_id: str,
    tutorial_title: str | None = None,
) -> RewardLedger | None:
    """Award points for finishing a guided learning tutorial (idempotent)."""
    return await award(
        session,
        user_id,
        source="learning",
        activity="tutorial_completed",
        points=POINTS_RULES["learning"]["tutorial_completed"],
        reference_key=f"tutorial:{tutorial_id}",
        description=f"Completed tutorial: {tutorial_title or tutorial_id}",
    )


async def award_roadmap_step(
    session: AsyncSession,
    user_id: uuid.UUID,
    roadmap_id: int,
    step_id: int,
    step_title: str | None = None,
) -> list[RewardLedger]:
    """Award points for completing a roadmap step.

    Also grants the ``roadmap_completed`` bonus when this completion finishes
    the last remaining step of the roadmap. Returns every ledger row created
    (empty when the step was already credited).
    """
    awarded: list[RewardLedger] = []
    module_entry = await award(
        session,
        user_id,
        source="learning",
        activity="module_completed",
        points=POINTS_RULES["learning"]["module_completed"],
        reference_key=f"roadmap:{roadmap_id}:step:{step_id}",
        description=f"Completed learning module: {step_title or f'step {step_id}'}",
        extra_metadata={"roadmap_id": roadmap_id, "step_id": step_id},
    )
    if module_entry is not None:
        awarded.append(module_entry)

        total_steps = await session.scalar(
            select(func.count(RoadmapStep.id)).where(RoadmapStep.roadmap_id == roadmap_id)
        )
        done_steps = await session.scalar(
            select(func.count(UserRoadmapProgress.id)).where(
                UserRoadmapProgress.roadmap_id == roadmap_id,
                UserRoadmapProgress.user_id == user_id,
                UserRoadmapProgress.completed.is_(True),
            )
        )
        if total_steps and done_steps and done_steps >= total_steps:
            bonus = await award(
                session,
                user_id,
                source="learning",
                activity="roadmap_completed",
                points=POINTS_RULES["learning"]["roadmap_completed"],
                reference_key=f"roadmap:{roadmap_id}:complete",
                description=f"Completed all modules of roadmap #{roadmap_id}",
                extra_metadata={"roadmap_id": roadmap_id},
            )
            if bonus is not None:
                awarded.append(bonus)
    return awarded


# ── GitHub activity sync ──

_GITHUB_EVENT_RULES: dict[str, list[tuple[str, str]]] = {
    # event type -> list of (activity, reference suffix); rules resolved per event below
}


def _map_github_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate one GitHub public event into zero or more award specs."""
    event_id = str(event.get("id") or uuid.uuid4())
    event_type = event.get("type")
    repo_name = (event.get("repo") or {}).get("name", "unknown repo")
    payload = event.get("payload") or {}
    occurred = event.get("created_at")
    occurred_at = (
        datetime.fromisoformat(occurred.replace("Z", "+00:00")) if isinstance(occurred, str) else None
    )
    rules = POINTS_RULES["github"]
    specs: list[dict[str, Any]] = []

    def spec(activity: str, reference: str, description: str) -> dict[str, Any]:
        return {
            "activity": activity,
            "points": rules[activity],
            "reference_key": f"gh:{event_id}:{reference}",
            "description": description,
            "occurred_at": occurred_at,
        }

    if event_type == "PushEvent":
        commits = payload.get("commits") or []
        if commits:
            for commit in commits:
                sha = str(commit.get("sha") or "")[:12]
                message = (commit.get("message") or "").splitlines()[0][:120]
                specs.append(
                    spec("commit", f"commit:{sha or uuid.uuid4()}", f"Pushed commit to {repo_name}: {message}")
                )
        else:
            specs.append(spec("commit", "push", f"Pushed to {repo_name}"))
    elif event_type == "PullRequestEvent":
        action = payload.get("action")
        pr = payload.get("pull_request") or {}
        pr_title = str(pr.get("title") or "")[:120]
        if action in {"opened", "reopened"}:
            specs.append(spec("pull_request", "pr", f"Opened pull request in {repo_name}: {pr_title}"))
        elif action == "closed" and pr.get("merged"):
            specs.append(
                spec("pull_request_merged", "merged", f"Merged pull request in {repo_name}: {pr_title}")
            )
    elif event_type == "IssuesEvent" and payload.get("action") == "opened":
        issue_title = str((payload.get("issue") or {}).get("title") or "")[:120]
        specs.append(spec("issue_opened", "issue", f"Opened issue in {repo_name}: {issue_title}"))
    elif event_type == "PullRequestReviewEvent":
        specs.append(spec("code_review", "review", f"Reviewed a pull request in {repo_name}"))
    elif event_type == "WatchEvent":
        specs.append(spec("starred_repo", "watch", f"Starred {repo_name}"))
    elif event_type == "ForkEvent":
        specs.append(spec("forked_repo", "fork", f"Forked {repo_name}"))

    return specs


async def sync_github_rewards(
    session: AsyncSession,
    user_id: uuid.UUID,
    github_username: str,
    token: str | None = None,
    max_pages: int = 3,
) -> dict[str, Any]:
    """Replay the user's recent public GitHub activity into the points ledger.

    Every event maps to per-activity awards deduplicated by GitHub event id,
    so calling this repeatedly only credits genuinely new activity.
    """
    awarded: list[RewardLedger] = []
    events_scanned = 0
    async with GitHubClient(token=token) as client:
        for page in range(1, max_pages + 1):
            events = await client.list_user_events(github_username, per_page=100, page=page)
            events_scanned += len(events)
            for event in events:
                for award_spec in _map_github_event(event):
                    entry = await award(
                        session,
                        user_id,
                        source="github",
                        activity=award_spec["activity"],
                        points=award_spec["points"],
                        reference_key=award_spec["reference_key"],
                        description=award_spec["description"],
                        occurred_at=award_spec["occurred_at"],
                    )
                    if entry is not None:
                        awarded.append(entry)
            if len(events) < 100:
                break

    return {
        "awarded": awarded,
        "total_awarded": sum(entry.points for entry in awarded),
        "events_scanned": events_scanned,
    }


# ── Claimable points (manual daily check-in) ──

DAILY_CLAIM_ID = "daily"


def _next_utc_midnight(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


async def get_claim_status(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> dict[str, Any]:
    """Describe the daily claim: amount, availability, and when it resets."""
    now = now or datetime.now(timezone.utc)
    reference = f"daily:{now.strftime('%Y-%m-%d')}"
    already = await session.scalar(
        select(RewardLedger.id).where(
            RewardLedger.user_id == user_id,
            RewardLedger.source == "daily",
            RewardLedger.activity == "login_claim",
            RewardLedger.reference_key == reference,
        )
    )
    available = already is None
    return {
        "id": DAILY_CLAIM_ID,
        "label": "Daily check-in",
        "points": POINTS_RULES["daily"]["login_claim"],
        "available": available,
        "next_available_at": None if available else _next_utc_midnight(now),
    }


async def claim_daily(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> tuple[RewardLedger | None, datetime]:
    """Claim today's check-in points (idempotent per UTC day)."""
    now = now or datetime.now(timezone.utc)
    entry = await award(
        session,
        user_id,
        source="daily",
        activity="login_claim",
        points=POINTS_RULES["daily"]["login_claim"],
        reference_key=f"daily:{now.strftime('%Y-%m-%d')}",
        description="Daily check-in",
    )
    return entry, _next_utc_midnight(now)


# ── Forum activity awards ──


async def award_forum_thread(
    session: AsyncSession, user_id: uuid.UUID, thread_id: int, title: str | None = None
) -> RewardLedger | None:
    """Award points for starting a discussion (idempotent per thread)."""
    return await award(
        session,
        user_id,
        source="forum",
        activity="thread_created",
        points=POINTS_RULES["forum"]["thread_created"],
        reference_key=f"forum:thread:{thread_id}",
        description=f"Started a discussion: {title or f'thread #{thread_id}'}",
        extra_metadata={"thread_id": thread_id},
    )


async def award_forum_reply(
    session: AsyncSession, user_id: uuid.UUID, thread_id: int, post_id: int
) -> RewardLedger | None:
    """Award points for replying to a discussion (idempotent per post)."""
    return await award(
        session,
        user_id,
        source="forum",
        activity="reply_posted",
        points=POINTS_RULES["forum"]["reply_posted"],
        reference_key=f"forum:post:{post_id}",
        description="Replied to a discussion",
        extra_metadata={"thread_id": thread_id, "post_id": post_id},
    )


async def award_forum_answer(
    session: AsyncSession, user_id: uuid.UUID, thread_id: int, post_id: int
) -> RewardLedger | None:
    """Award points to the author whose reply was accepted (idempotent)."""
    return await award(
        session,
        user_id,
        source="forum",
        activity="answer_accepted",
        points=POINTS_RULES["forum"]["answer_accepted"],
        reference_key=f"forum:accepted:{thread_id}:{post_id}",
        description="Your reply was accepted as the solution",
        extra_metadata={"thread_id": thread_id, "post_id": post_id},
    )


async def award_forum_upvote(
    session: AsyncSession, user_id: uuid.UUID, post_id: int, voter_id: uuid.UUID
) -> RewardLedger | None:
    """Award the post author when someone upvotes (idempotent per voter)."""
    return await award(
        session,
        user_id,
        source="forum",
        activity="upvote_received",
        points=POINTS_RULES["forum"]["upvote_received"],
        reference_key=f"forum:upvote:{post_id}:{voter_id}",
        description="Your forum post received an upvote",
        extra_metadata={"post_id": post_id},
    )


# ── Redemptions (spend points) ──


async def redeem(
    session: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    description: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> RewardLedger:
    """Spend points on a reward. Raises ValueError when the balance is too low."""
    if amount <= 0:
        raise ValueError("Redemption amount must be positive.")
    balance = await get_balance(session, user_id)
    if balance < amount:
        raise ValueError(f"Insufficient balance: {balance} points available, {amount} required.")

    entry = RewardLedger(
        user_id=user_id,
        source="redemption",
        activity="mentor_session",
        points=-amount,
        reference_key=f"redemption:{uuid.uuid4()}",
        description=_clip(description),
        extra_metadata=extra_metadata,
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def cancel_redemption(
    session: AsyncSession,
    user_id: uuid.UUID,
    reference_key: str,
) -> bool:
    """Refund a redemption by deleting its negative ledger row."""
    result = await session.execute(
        delete(RewardLedger).where(
            RewardLedger.user_id == user_id,
            RewardLedger.source == "redemption",
            RewardLedger.reference_key == reference_key,
        )
    )
    await session.commit()
    return result.rowcount > 0
