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
from apps.api.db.vault import get_or_create_db_encryption_key

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

# Attach SQLCipher encryption key and durability pragmas for SQLite databases
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        key = get_or_create_db_encryption_key()
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA key = '{key}'")
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
        except Exception:
            pass
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
