"""Rewards system tests: awards, idempotency, redemptions, GitHub sync."""

import uuid
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.database import Base, get_db
from backend.core.jwt import create_access_token
from backend.core.security import hash_password
from backend.main import app
from backend.models.reward_model import RewardLedger
from backend.models.roadmap import Roadmap
from backend.models.roadmap_step import RoadmapStep
from backend.models.user_model import User
from backend.services import rewards_service
from backend.services.roadmap_service import upsert_progress
from backend.schemas.roadmaps import ProgressCreate


@pytest_asyncio.fixture
async def rewards_db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()

    user = User(
        id=uuid.uuid4(),
        email="contributor@example.com",
        username="contributor",
        password_hash=hash_password("password-123"),
        role="user",
        account_status="active",
        is_active=True,
    )
    session.add(user)
    await session.commit()

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    yield session, user
    app.dependency_overrides.clear()
    await session.close()
    await engine.dispose()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


# ── Service-level awards ──


@pytest.mark.asyncio
async def test_award_is_idempotent_per_reference(rewards_db) -> None:
    session, user = rewards_db
    first = await rewards_service.award(
        session, user.id, "github", "commit", 5, reference_key="gh:1:commit:abc"
    )
    replay = await rewards_service.award(
        session, user.id, "github", "commit", 5, reference_key="gh:1:commit:abc"
    )
    assert first is not None
    assert replay is None
    assert await rewards_service.get_balance(session, user.id) == 5


@pytest.mark.asyncio
async def test_roadmap_step_completion_awards_module_and_roadmap_bonus(rewards_db) -> None:
    session, user = rewards_db
    roadmap = Roadmap(name="OSS Roadmap", description=None)
    session.add(roadmap)
    await session.flush()
    step_a = RoadmapStep(
        roadmap_id=roadmap.id, day_number=1, title="Git basics", step_order=1
    )
    step_b = RoadmapStep(
        roadmap_id=roadmap.id, day_number=2, title="First PR", step_order=2
    )
    session.add_all([step_a, step_b])
    await session.commit()

    await upsert_progress(
        session,
        ProgressCreate(
            user_id=user.id, roadmap_id=roadmap.id, step_id=step_a.id, completed=True
        ),
    )
    # Re-completing the same step must not double-credit.
    await upsert_progress(
        session,
        ProgressCreate(
            user_id=user.id, roadmap_id=roadmap.id, step_id=step_a.id, completed=True
        ),
    )
    await upsert_progress(
        session,
        ProgressCreate(
            user_id=user.id, roadmap_id=roadmap.id, step_id=step_b.id, completed=True
        ),
    )

    entries = list((await session.execute(select(RewardLedger))).scalars())
    activities = sorted((entry.activity, entry.points) for entry in entries)
    assert activities == [
        ("module_completed", 30),
        ("module_completed", 30),
        ("roadmap_completed", 100),
    ]
    assert await rewards_service.get_balance(session, user.id) == 160


# ── API: learning tutorial award ──


@pytest.mark.asyncio
async def test_tutorial_award_route_is_idempotent(rewards_db) -> None:
    _session, user = rewards_db
    payload = {"tutorial_id": "git-101", "tutorial_title": "Git Basics"}
    async with _client() as client:
        first = await client.post(
            "/api/v1/rewards/tutorial-completed", json=payload, headers=_headers(user)
        )
        replay = await client.post(
            "/api/v1/rewards/tutorial-completed", json=payload, headers=_headers(user)
        )
        summary = await client.get("/api/v1/rewards/me", headers=_headers(user))
    assert first.status_code == 200
    assert first.json() == {"awarded": True, "points": 20, "balance": 20}
    assert replay.json() == {"awarded": False, "points": 0, "balance": 20}

    body = summary.json()
    assert body["balance"] == 20
    assert body["breakdown"] == {"learning": 20}
    assert body["rules"]["learning"]["tutorial_completed"] == 20
    assert body["recent"][0]["activity"] == "tutorial_completed"


@pytest.mark.asyncio
async def test_rewards_routes_require_auth(rewards_db) -> None:
    async with _client() as client:
        response = await client.get("/api/v1/rewards/me")
    assert response.status_code == 401


# ── API: redemptions ──


@pytest.mark.asyncio
async def test_redeem_rejects_insufficient_balance(rewards_db) -> None:
    _session, user = rewards_db
    async with _client() as client:
        response = await client.post(
            "/api/v1/rewards/redeem",
            json={"amount": 100, "mentor_name": "Aarav Mehta"},
            headers=_headers(user),
        )
    assert response.status_code == 400
    assert "Insufficient balance" in response.json()["detail"]


@pytest.mark.asyncio
async def test_redeem_and_cancel_refund_flow(rewards_db) -> None:
    session, user = rewards_db
    await rewards_service.award(
        session, user.id, "learning", "module_completed", 150, reference_key="roadmap:1:step:1"
    )
    async with _client() as client:
        redeem = await client.post(
            "/api/v1/rewards/redeem",
            json={
                "amount": 100,
                "mentor_id": 1,
                "mentor_name": "Aarav Mehta",
                "tier": "beginner",
                "date": "2026-10-10",
                "time": "10:00",
                "topic": "First PR review",
            },
            headers=_headers(user),
        )
        assert redeem.status_code == 200
        body = redeem.json()
        assert body["balance"] == 50
        assert body["redemption"]["points"] == -100
        assert body["redemption"]["extra_metadata"]["mentor_name"] == "Aarav Mehta"

        reference = body["redemption"]["reference_key"]
        ledger = await client.get(
            "/api/v1/rewards/ledger?limit=10", headers=_headers(user)
        )
        assert ledger.status_code == 200
        assert ledger.json()["total"] == 2

        cancel = await client.post(
            "/api/v1/rewards/redemptions/cancel",
            json={"reference_key": reference},
            headers=_headers(user),
        )
        assert cancel.status_code == 200
        assert cancel.json() == {"refunded": True, "balance": 150}

        again = await client.post(
            "/api/v1/rewards/redemptions/cancel",
            json={"reference_key": reference},
            headers=_headers(user),
        )
        assert again.json() == {"refunded": False, "balance": 150}


# ── GitHub activity sync ──


class _FakeGitHubClient:
    """Stands in for GitHubClient and replays canned public events."""

    events: list[dict[str, Any]] = []

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    async def __aenter__(self) -> "_FakeGitHubClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def list_user_events(
        self, username: str, per_page: int = 30, page: int = 1
    ) -> list[dict[str, Any]]:
        return self.events if page == 1 else []


def _canned_events() -> list[dict[str, Any]]:
    return [
        {
            "id": "1001",
            "type": "PushEvent",
            "repo": {"name": "me/repo"},
            "created_at": "2026-10-05T10:00:00Z",
            "payload": {
                "commits": [
                    {"sha": "a" * 40, "message": "fix: crash on empty input"},
                    {"sha": "b" * 40, "message": "docs: update readme"},
                ]
            },
        },
        {
            "id": "1002",
            "type": "PullRequestEvent",
            "repo": {"name": "me/repo"},
            "created_at": "2026-10-05T11:00:00Z",
            "payload": {
                "action": "closed",
                "pull_request": {"title": "Add search", "merged": True},
            },
        },
        {
            "id": "1003",
            "type": "PullRequestEvent",
            "repo": {"name": "me/repo"},
            "created_at": "2026-10-05T12:00:00Z",
            "payload": {
                "action": "opened",
                "pull_request": {"title": "WIP feature", "merged": False},
            },
        },
        {
            "id": "1004",
            "type": "IssuesEvent",
            "repo": {"name": "me/repo"},
            "created_at": "2026-10-05T13:00:00Z",
            "payload": {"action": "opened", "issue": {"title": "Bug report"}},
        },
        {
            "id": "1005",
            "type": "PullRequestReviewEvent",
            "repo": {"name": "me/repo"},
            "created_at": "2026-10-05T14:00:00Z",
            "payload": {"action": "created"},
        },
        {
            "id": "1006",
            "type": "WatchEvent",
            "repo": {"name": "me/repo"},
            "created_at": "2026-10-05T15:00:00Z",
            "payload": {"action": "started"},
        },
        {"id": "1007", "type": "IssueCommentEvent", "repo": {"name": "me/repo"}, "payload": {}},
    ]


@pytest.mark.asyncio
async def test_sync_github_rewards_maps_events_and_is_idempotent(
    rewards_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, user = rewards_db
    _FakeGitHubClient.events = _canned_events()
    monkeypatch.setattr(rewards_service, "GitHubClient", _FakeGitHubClient)

    result = await rewards_service.sync_github_rewards(session, user.id, "contributor")
    # Two commits (5 each), merged PR (50), opened PR (25), issue (10),
    # review (15), star (2). IssueComment maps to nothing.
    assert result["total_awarded"] == 5 * 2 + 50 + 25 + 10 + 15 + 2
    assert result["events_scanned"] == 7

    balance_after_first = await rewards_service.get_balance(session, user.id)
    assert balance_after_first == result["total_awarded"]

    replay = await rewards_service.sync_github_rewards(session, user.id, "contributor")
    assert replay["total_awarded"] == 0
    assert await rewards_service.get_balance(session, user.id) == balance_after_first


@pytest.mark.asyncio
async def test_sync_github_route_requires_linked_github_account(rewards_db) -> None:
    _session, user = rewards_db
    async with _client() as client:
        response = await client.post("/api/v1/rewards/sync-github", headers=_headers(user))
    assert response.status_code == 400
    assert "Link a GitHub account" in response.json()["detail"]
