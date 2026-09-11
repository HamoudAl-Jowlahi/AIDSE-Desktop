"""
AIDSE Platform — Async Database Session
Section 10 (Database Design), Section 23.4 (Coding Standards)

Uses SQLAlchemy 2.x async engine with asyncpg for high-throughput
concurrent evaluation runs (Section 8.4 — <200ms prediction latency target).

ADR-002: Async SQLAlchemy chosen for concurrent eval run support.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.core.config import get_settings

settings = get_settings()

from sqlalchemy import event

# Configure engine parameters depending on dialect (SQLite vs Postgres)
engine_kwargs = {
    "echo": bool(getattr(settings, "SQL_ECHO", False)),
}

if "sqlite" in settings.DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update({
        "pool_size": 20,
        "max_overflow": 40,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    })

# Single engine per process — connection pool shared across requests
engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)

# Durability and integrity pragmas for SQLite.
#
# There is deliberately no `PRAGMA key` here. This engine talks to SQLite
# through aiosqlite/the stdlib `sqlite3` module, where `PRAGMA key` is a
# silent no-op — it accepted the statement and wrote a plaintext database,
# which is what earlier builds shipped while the docs claimed SQLCipher.
# Sensitive column values are encrypted at the application layer instead
# (apps/api/core/crypto.py).
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
        finally:
            cursor.close()

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,       # Avoid implicit I/O after commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yield an async DB session, auto-close on exit.
    Used via: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
