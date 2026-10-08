"""Tests for remember-me sessions, the production PAT-login gate, and real GitHub streaks."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.api import auth as auth_module
from backend.core.config import settings
from backend.core.database import Base, get_db
from backend.core.jwt import create_access_token, decode_access_token
from backend.core.security import hash_password
from backend.main import app
from backend.models.user_model import User
from backend.services.github_service import _compute_streak_days


@pytest_asyncio.fixture
async def auth_flow_db(monkeypatch: pytest.MonkeyPatch):
    """Isolated DB with one verified user plus captured OTP emails."""
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
        email="remember@example.com",
        username="remember_me",
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


# ── Remember me ──


@pytest.mark.asyncio
async def test_login_default_token_lives_about_two_hours(auth_flow_db) -> None:
    _session, user = auth_flow_db
    async with _client() as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "remember@example.com", "password": "password-123"},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["expires_at"] is not None

    payload = decode_access_token(body["access_token"])
    assert payload is not None
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    lifetime = expires_at - datetime.now(UTC)
    assert timedelta(minutes=110) < lifetime < timedelta(minutes=130)


@pytest.mark.asyncio
async def test_login_remember_me_token_lives_one_day(auth_flow_db) -> None:
    _session, user = auth_flow_db
    async with _client() as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "remember@example.com",
                "password": "password-123",
                "remember_me": True,
            },
        )
    assert res.status_code == 200
    body = res.json()

    payload = decode_access_token(body["access_token"])
    assert payload is not None
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    lifetime = expires_at - datetime.now(UTC)
    # One full day, with slack for test latency.
    assert timedelta(minutes=1430) < lifetime < timedelta(minutes=1450)

    # Response expiry must match the token claim within seconds.
    response_expiry = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert abs((response_expiry - expires_at).total_seconds()) < 5


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(auth_flow_db) -> None:
    _session, _user = auth_flow_db
    async with _client() as client:
        res = await client.post(
            "/api/v1/auth/login",
            json={"email": "remember@example.com", "password": "wrong-password"},
        )
    assert res.status_code == 401


# ── Production gate on the dev-only PAT login ──


@pytest.mark.asyncio
async def test_pat_login_disabled_in_production(auth_flow_db, monkeypatch: pytest.MonkeyPatch) -> None:
    _session, _user = auth_flow_db
    monkeypatch.setattr(auth_module.settings, "ENVIRONMENT", "production")
    async with _client() as client:
        res = await client.post("/api/v1/auth/github/pat-login")
    assert res.status_code == 404
    assert "production" in res.json()["detail"]


@pytest.mark.asyncio
async def test_pat_login_available_in_development_without_token_returns_400(
    auth_flow_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    _session, _user = auth_flow_db
    monkeypatch.setattr(auth_module.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(auth_module.settings, "GITHUB_TOKEN", "")
    async with _client() as client:
        res = await client.post("/api/v1/auth/github/pat-login")
    assert res.status_code == 400
    assert "GITHUB_TOKEN" in res.json()["detail"]


# ── Real GitHub streak computation ──


def test_streak_counts_consecutive_days_ending_today() -> None:
    today = datetime.now(UTC).date()
    dates = {
        (today - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(4)
    }
    assert _compute_streak_days(dates, today) == 4


def test_streak_accepts_gap_starting_yesterday() -> None:
    today = datetime.now(UTC).date()
    dates = {
        (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(1, 6)  # active yesterday..5 days ago, not today
    }
    assert _compute_streak_days(dates, today) == 5


def test_streak_zero_when_no_recent_activity() -> None:
    today = datetime.now(UTC).date()
    dates = {(today - timedelta(days=10)).strftime("%Y-%m-%d")}
    assert _compute_streak_days(dates, today) == 0


def test_streak_empty_activity_is_zero() -> None:
    today = datetime.now(UTC).date()
    assert _compute_streak_days(set(), today) == 0
