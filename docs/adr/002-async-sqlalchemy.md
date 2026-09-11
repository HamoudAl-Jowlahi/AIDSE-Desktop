# ADR-002: Async SQLAlchemy (asyncpg) over Sync ORM
**Date:** 2026-06-28
**Status:** Accepted
**Section Reference:** Section 8.4 (Performance targets), Section 9.1 (Architecture)

---

## Context

AIDSE's critical performance requirement (Section 8.4):
- Evaluation run with 100 golden cases: < 5 minutes
- Prediction API response: < 200ms p95

Evaluation runs make many concurrent I/O-bound calls:
- N calls to the AI provider (one per golden case, parallelizable)
- N DB writes (one per result)
- Multiple DB reads (golden dataset, run metadata, baseline)

Two ORM options:

1. **Synchronous SQLAlchemy**: simple, widely documented, but blocks the event loop on every DB call
2. **Async SQLAlchemy 2.x with asyncpg**: non-blocking, enables true async concurrency across DB operations

---

## Decision

**Async SQLAlchemy 2.x + asyncpg** for all database access throughout the platform.

---

## Consequences

### Positive
- The FastAPI/uvicorn event loop is never blocked on DB I/O — requests remain responsive during long-running queries
- Evaluation workers can parallelize DB writes without thread pool overhead
- asyncpg is the fastest PostgreSQL driver for Python (binary protocol, no psycopg2 overhead)

### Negative / Trade-offs
- **Syntax overhead**: `async with session:`, `await session.execute()`, `await session.scalar()` — slightly more verbose than sync ORM
- **Testing complexity**: requires `pytest-asyncio` and an async test DB (mitigated by using `aiosqlite` in-memory for unit tests, avoiding external DB in CI)
- **Less Stack Overflow coverage**: async SQLAlchemy patterns are less commonly documented than sync ORM. Agent must be careful not to mix sync and async patterns.

### Mitigation
- All DB access is centralized in `service.py` per module — no ORM calls in routers or templates
- `conftest.py` provides `aiosqlite` in-memory fixtures so tests run without Docker
- Session factory documented in `db/session.py` with clear comments

---

*ADR format: Context → Decision → Consequences. Section 23.6.*
