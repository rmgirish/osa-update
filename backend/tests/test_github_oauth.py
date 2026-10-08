"""Unit tests for GitHub OAuth flow and dev PAT endpoints."""

import urllib.parse

import httpx
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.core.config import settings
from backend.services.github_oauth_service import GitHubOAuthService


@pytest.mark.asyncio
async def test_oauth_authorization_and_exchange_use_same_callback_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Send the registered callback URI in both steps using form encoding."""
    callback_uri = "https://app.example.com/api/v1/auth/github/callback"
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "GITHUB_REDIRECT_URI", callback_uri)

    authorization_url = GitHubOAuthService.get_authorization_url(state="test-state")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(authorization_url).query)
    assert query["redirect_uri"] == [callback_uri]
    assert query["state"] == ["test-state"]

    captured_request: httpx.Request | None = None

    async def mock_post(
        _client: httpx.AsyncClient,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        nonlocal captured_request
        captured_request = httpx.Request("POST", url, data=data, headers=headers)
        return httpx.Response(200, json={"access_token": "mock_access_token"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    token = await GitHubOAuthService.exchange_code_for_token("mock_code")

    assert token == "mock_access_token"
    assert captured_request is not None
    assert captured_request.headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    body = urllib.parse.parse_qs(captured_request.content.decode())
    assert body["client_id"] == ["mock_client_id"]
    assert body["client_secret"] == ["mock_client_secret"]
    assert body["code"] == ["mock_code"]
    assert body["redirect_uri"] == [callback_uri]


def test_oauth_callback_uri_falls_back_to_frontend_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "GITHUB_REDIRECT_URI", " ")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.example.com/")

    authorization_url = GitHubOAuthService.get_authorization_url()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(authorization_url).query)

    assert query["redirect_uri"] == [
        "https://app.example.com/api/v1/auth/github/callback"
    ]


@pytest.mark.asyncio
async def test_get_github_oauth_url_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test /api/v1/auth/github/url when GITHUB_CLIENT_ID is not configured."""
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", None)
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/auth/github/url")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is False
        assert data["url"] is None
        assert data["has_pat"] is False


@pytest.mark.asyncio
async def test_get_github_oauth_url_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test /api/v1/auth/github/url when OAuth is configured."""
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "mock_token")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/auth/github/url")
        assert res.status_code == 200
        data = res.json()
        assert data["configured"] is True
        assert "github.com/login/oauth/authorize" in data["url"]
        assert "client_id=mock_client_id" in data["url"]
        assert data["has_pat"] is True


@pytest.mark.asyncio
async def test_github_oauth_callback_missing_code() -> None:
    """Test /api/v1/auth/github/callback redirects to error when code is missing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/auth/github/callback", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert "oauth_error=" in res.headers["location"]


@pytest.mark.asyncio
async def test_github_oauth_callback_with_error() -> None:
    """Test /api/v1/auth/github/callback redirects when error is passed."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/auth/github/callback?error=access_denied&error_description=User%20cancelled",
            follow_redirects=False,
        )
        assert res.status_code in (302, 307)
        assert "oauth_error=" in res.headers["location"]
        assert "User+cancelled" in res.headers["location"] or "User%20cancelled" in res.headers["location"]


@pytest.mark.asyncio
async def test_github_pat_login_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test /api/v1/auth/github/pat-login with mocked profile fetch."""
    monkeypatch.setattr(settings, "GITHUB_TOKEN", "mock_pat_token")

    async def mock_fetch_github_user(token: str) -> dict[str, str]:
        return {
            "github_id": 99999,
            "login": "octocat-dev",
            "name": "The Octocat",
            "email": "octocat-dev@github.com",
            "avatar_url": "https://github.com/octocat.png",
        }

    monkeypatch.setattr(GitHubOAuthService, "fetch_github_user", mock_fetch_github_user)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post("/api/v1/auth/github/pat-login")
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert "octocat-dev" in data["message"]
