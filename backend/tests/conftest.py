"""Test-only environment defaults, loaded before application imports."""

import os
import tempfile
from pathlib import Path

# File-backed SQLite database shared by every test that does not override the
# ``get_db`` dependency. A file (instead of an unnamed in-memory DB) is required
# because SQLAlchemy async engines open multiple connections, and each
# connection to an unnamed in-memory SQLite database sees a separate empty DB.
_TMP_DIR = tempfile.mkdtemp(prefix="open-source-assist-tests-")
_TEST_DB_PATH = Path(_TMP_DIR) / "test.db"

TEST_SETTINGS = {
    "ENVIRONMENT": "testing",
    "API_V1_PREFIX": "/api/v1",
    "DATABASE_URL": f"sqlite+aiosqlite:///{_TEST_DB_PATH.as_posix()}",
    "JWT_SECRET_KEY": "test-secret-key",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
    "OTP_EXPIRE_MINUTES": "5",
    "SERVER_HOST": "127.0.0.1",
    "SERVER_PORT": "8000",
    "SERVER_RELOAD": "false",
    "CORS_ALLOW_ORIGINS": "http://test",
    "CORS_ALLOW_CREDENTIALS": "true",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_API_KEY": "",
    "QDRANT_PREFER_GRPC": "false",
    "QDRANT_COLLECTION_NAME": "test_repositories",
    "QDRANT_VECTOR_SIZE": "384",
    "EMBEDDING_MODEL_NAME": "BAAI/bge-small-en-v1.5",
    "DEFAULT_POPULARITY_WEIGHT": "0.3",
    "CANDIDATE_SEARCH_LIMIT": "100",
    "DEFAULT_PAGE_LIMIT": "20",
}

for key, value in TEST_SETTINGS.items():
    os.environ.setdefault(key, value)

import asyncio  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_global_test_tables():
    """Create all ORM tables on the shared global test engine once per session.

    Tests that build their own engines (e.g. auth tests) are unaffected; this
    only guarantees that the app's default ``get_db`` dependency works without
    a running PostgreSQL server.
    """
    import backend.models  # noqa: F401
    from backend.core.database import Base, engine

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    yield
    asyncio.run(engine.dispose())
