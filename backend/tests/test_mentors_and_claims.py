"""Tests for the mentors catalog, the daily claim, and forum activity points."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.database import Base, get_db
from backend.core.jwt import create_access_token
from backend.core.security import hash_password
from backend.main import app
from backend.models.user_model import User
from backend.services import rewards_service


@pytest_asyncio.fixture
async def db_user():
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
        email="mentee@example.com",
        username="mentee",
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


# ── Mentors catalog ──


@pytest.mark.asyncio
async def test_mentors_catalog_is_seeded_and_paginates_tiers(db_user) -> None:
    async with _client() as client:
        response = await client.get("/api/v1/mentors")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 6
    assert len(body["mentors"]) == 6
    assert body["tiers"] == {
        "beginner": 100,
        "intermediate": 300,
        "advanced": 600,
        "expert": 1000,
    }
    # Ordered cheapest first.
    costs = [m["cost"] for m in body["mentors"]]
    assert costs == sorted(costs)
    assert {m["tier"] for m in body["mentors"]} == {
        "beginner",
        "intermediate",
        "advanced",
        "expert",
    }


@pytest.mark.asyncio
async def test_mentors_can_be_filtered_by_tag(db_user) -> None:
    async with _client() as client:
        response = await client.get("/api/v1/mentors", params={"tag": "Docker"})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["mentors"][0]["name"] == "Priya Sharma"


# ── Daily claim ──


@pytest.mark.asyncio
async def test_daily_claim_awards_then_goes_on_cooldown(db_user) -> None:
    _session, user = db_user
    async with _client() as client:
        before = await client.get("/api/v1/rewards/claims", headers=_headers(user))
        first = await client.post("/api/v1/rewards/claims/daily", headers=_headers(user))
        replay = await client.post("/api/v1/rewards/claims/daily", headers=_headers(user))
        after = await client.get("/api/v1/rewards/claims", headers=_headers(user))

    assert before.status_code == 200
    claim = before.json()["claims"][0]
    assert claim["id"] == "daily"
    assert claim["points"] == 25
    assert claim["available"] is True

    assert first.status_code == 200
    first_body = first.json()
    assert first_body["awarded"] is True
    assert first_body["points"] == 25
    assert first_body["balance"] == 25
    assert first_body["next_available_at"] is not None

    assert replay.json()["awarded"] is False
    assert replay.json()["balance"] == 25

    cooled = after.json()["claims"][0]
    assert cooled["available"] is False
    assert cooled["next_available_at"] is not None


@pytest.mark.asyncio
async def test_claims_require_auth(db_user) -> None:
    async with _client() as client:
        response = await client.get("/api/v1/rewards/claims")
    assert response.status_code == 401


# ── Forum activity points ──


@pytest.mark.asyncio
async def test_creating_thread_and_replying_award_points(db_user) -> None:
    _session, user = db_user
    async with _client() as client:
        created = await client.post(
            "/api/v1/forum/threads",
            json={"title": "How do I rebase?", "content": "Question body", "category": "q-and-a"},
            headers=_headers(user),
        )
        assert created.status_code == 201
        thread_id = created.json()["id"]

        replied = await client.post(
            f"/api/v1/forum/threads/{thread_id}/replies",
            json={"content": "Try `git rebase --continue`."},
            headers=_headers(user),
        )
        assert replied.status_code == 201

        summary = await client.get("/api/v1/rewards/me", headers=_headers(user))

    body = summary.json()
    # 15 for the thread + 5 for the reply.
    assert body["balance"] == 20
    assert body["breakdown"]["forum"] == 20
    assert body["rules"]["forum"]["thread_created"] == 15
    assert body["rules"]["forum"]["reply_posted"] == 5


@pytest.mark.asyncio
async def test_forum_award_helpers_are_idempotent(db_user) -> None:
    session, user = db_user
    first = await rewards_service.award_forum_thread(session, user.id, 42, "Title")
    replay = await rewards_service.award_forum_thread(session, user.id, 42, "Title")
    assert first is not None
    assert replay is None
    assert await rewards_service.get_balance(session, user.id) == 15

    voter = uuid.uuid4()
    upvote = await rewards_service.award_forum_upvote(session, user.id, 7, voter)
    same_voter = await rewards_service.award_forum_upvote(session, user.id, 7, voter)
    other_voter = await rewards_service.award_forum_upvote(session, user.id, 7, uuid.uuid4())
    assert upvote is not None
    assert same_voter is None  # the same voter never double-credits
    assert other_voter is not None  # a distinct voter credits again
    # 15 (thread) + 2 + 2 (two distinct upvotes).
    assert await rewards_service.get_balance(session, user.id) == 15 + 2 + 2
