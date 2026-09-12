"""
AIDSE Platform — pytest fixtures for integration tests
Section 23.5 (Testing Standards)

Provides:
- In-memory SQLite database for tests (no external DB needed in CI)
- HTTPX AsyncClient with app mounted
- Convenience fixtures: registered_user, logged_in_user, auth_headers, etc.
"""
from __future__ import annotations

import os

# Rate limiter off for the suite (individual limiter tests re-enable it).
# Must be set BEFORE any app/settings import.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("CELERY_TASK_EAGER_PROPAGATES", "true")
# No broker runs in CI, so dispatching an experiment would otherwise fall back to
# fitting real models in-process and make the suite take minutes. Tests that want
# training exercise the service layer directly.
os.environ.setdefault("LOCAL_TRAINING_FALLBACK", "false")
# Deterministic key material so the vault never touches the developer's real
# OS credential store during a test run.
os.environ.setdefault("AIDSE_APP_SECRET", "0" * 64)

# Keep the suite out of the user's real data directory. Without this,
# get_aidse_data_dir() falls back to %LOCALAPPDATA%\AIDSE-Desktop and every
# upload test writes a dataset folder into the live install — a full run left
# well over a hundred orphaned directories behind.
import tempfile as _tempfile

os.environ.setdefault(
    "AIDSE_DATA_DIR",
    os.path.join(_tempfile.gettempdir(), "aidse-test-data"),
)

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.db.base import Base
from apps.api.db.session import get_db

# Import every model module so Base.metadata is fully populated BEFORE
# create_all runs. Models are otherwise registered lazily (create_app()
# imports routers during the first test), which used to leave tables missing.
from apps.api.modules.auth.models import User  # noqa: F401
from apps.api.modules.automl.models import Experiment, ModelTrial  # noqa: F401
from apps.api.modules.datasets.models import (  # noqa: F401
    Dataset,
    DatasetVersion,
    GoldenCase,
    GoldenDataset,
    ProviderCredential,
)
from apps.api.modules.evaluation.models import (  # noqa: F401
    EvaluationResult,
    EvaluationRun,
    RegressionReport,
    RegressionReportCase,
    ScheduledEvaluation,
)
from apps.api.modules.conversational.models import ChatMessage, Conversation  # noqa: F401
from apps.api.modules.projects.models import AuditLog, Project, ProjectMember  # noqa: F401

# Use SQLite in-memory for tests (no Docker needed in CI)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_test_tables() -> AsyncGenerator[None, None]:
    """Create all tables in the test DB before the session, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables_between_tests() -> AsyncGenerator[None, None]:
    """
    Truncate every table after each test for isolation.

    A rollback-per-test strategy does not survive endpoint code that calls
    session.commit() (uploads, registrations...), so we truncate instead.
    Requires all model modules imported up front (done above).
    """
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a test DB session."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client wired to the FastAPI app with overridden DB."""
    from apps.api.main import create_app

    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


# ── Convenience fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a user and return the payload including raw password."""
    payload = {
        "name": "Alice Test",
        "email": "alice@test.example.com",
        "password": "AlicePass1",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    return {**payload, **resp.json()}


@pytest_asyncio.fixture
async def logged_in_user(client: AsyncClient, registered_user: dict) -> dict:
    """Register + login and return tokens + credentials."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    data = {**registered_user, **resp.json()}
    # Extract refresh token from cookie (now HttpOnly)
    refresh_cookie = client.cookies.get("refresh_token")
    if refresh_cookie:
        data["refresh_token"] = refresh_cookie
    return data


@pytest_asyncio.fixture
async def auth_headers(logged_in_user: dict) -> dict:
    """Authorization headers for an authenticated user."""
    return {"Authorization": f"Bearer {logged_in_user['access_token']}"}


@pytest_asyncio.fixture
async def second_user(client: AsyncClient) -> dict:
    """A second registered user (for testing invites/multi-user scenarios)."""
    payload = {
        "name": "Bob Test",
        "email": "bob@test.example.com",
        "password": "BobPass1",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201
    return {**payload, **resp.json()}


@pytest_asyncio.fixture
async def second_user_headers(client: AsyncClient, second_user: dict) -> dict:
    """Auth headers for the second user."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": second_user["email"], "password": second_user["password"]},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
