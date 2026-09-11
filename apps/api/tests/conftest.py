"""
AIDSE Platform — pytest fixtures for integration tests
Section 23.5 (Testing Standards)

Uses SQLite in-memory (aiosqlite) — no external DB needed in CI.
Creates tables once per session; each test runs in an isolated async session.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.db.base import Base  # noqa: F401
from apps.api.db.session import get_db

# Import all models so Base.metadata is populated
from apps.api.modules.auth.models import User  # noqa: F401
from apps.api.modules.projects.models import AuditLog, Project, ProjectMember  # noqa: F401
from apps.api.modules.datasets.models import Dataset, DatasetVersion, GoldenDataset, GoldenCase, ProviderCredential  # noqa: F401
from apps.api.modules.evaluation.models import EvaluationRun, EvaluationResult, RegressionReport, RegressionReportCase, ScheduledEvaluation  # noqa: F401
from apps.api.modules.automl.models import Experiment, ModelTrial  # noqa: F401
# ── Engine (shared per session) ────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:?check_same_thread=false"

_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
_SessionLocal = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables() -> AsyncGenerator[None, None]:
    """Create all tables before the test session, drop after."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clear_tables() -> AsyncGenerator[None, None]:
    """Truncate all tables before each test for isolation (faster than rollback)."""
    yield
    async with _engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh DB session per test."""
    async with _SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client with FastAPI app + DB override."""
    from apps.api.main import create_app

    app = create_app()

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


# ── Convenience fixtures ──────────────────────────────────────────────────

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    """Register a user and return credentials."""
    payload = {
        "name": "Alice Test",
        "email": "alice@test.example.com",
        "password": "AlicePass1!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return {**payload, **resp.json()}


@pytest_asyncio.fixture
async def logged_in_user(client: AsyncClient, registered_user: dict) -> dict:
    """Register + login."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": registered_user["email"],
            "password": registered_user["password"],
        },
    )
    assert resp.status_code == 200, resp.text
    return {**registered_user, **resp.json()}


@pytest_asyncio.fixture
async def auth_headers(logged_in_user: dict) -> dict:
    """Bearer auth headers for primary user."""
    return {"Authorization": f"Bearer {logged_in_user['access_token']}"}


@pytest_asyncio.fixture
async def second_user(client: AsyncClient) -> dict:
    """A second registered user."""
    payload = {
        "name": "Bob Test",
        "email": "bob@test.example.com",
        "password": "BobPass1!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return {**payload, **resp.json()}


@pytest_asyncio.fixture
async def second_user_headers(client: AsyncClient, second_user: dict) -> dict:
    """Bearer auth headers for second user."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": second_user["email"], "password": second_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
