"""
AIDSE Platform — FastAPI Application Entrypoint
Section 9.1 (System Architecture), Section 12.1 (Folder Structure)
Section 8.2 (Security), Section 13.6 (Rate Limiting)

Factory pattern used (create_app()) to support:
- Testing: test client can create a fresh app with overridden dependencies
- Production: single app instance per worker process
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan: startup checks → yield → shutdown cleanup.
    Runs once per worker process.
    """
    # Startup: headless DB migrations & connection check
    import asyncio

    from apps.api.db.migrations_runner import run_migrations_headless
    from apps.api.db.session import engine
    from apps.api.db.base import Base
    from sqlalchemy import text

    try:
        # Alembic's env.py drives an async engine via asyncio.run(), which
        # cannot be called from inside this already-running loop. A worker
        # thread has no loop of its own, so it runs there — and migrations
        # stay off the event loop, which they should be regardless.
        await asyncio.to_thread(run_migrations_headless)
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            if "sqlite" in str(engine.url):
                # Imported so the models register on Base.metadata. They are
                # not imported to build the schema — Alembic above does that.
                import apps.api.modules.auth.models  # noqa
                import apps.api.modules.projects.models  # noqa
                import apps.api.modules.datasets.models  # noqa
                import apps.api.modules.evaluation.models  # noqa
                import apps.api.modules.automl.models  # noqa
                import apps.api.modules.conversational.models  # noqa

                # Early builds stored UUIDs with native UUID affinity; the models now
                # use CHAR(32). A mismatched table still reads and writes correctly in
                # SQLite (affinity is advisory), so report it and let a migration fix
                # it — never drop the table, which would destroy the user's work.
                import logging as _logging
                tbl_rows = (await conn.execute(text("SELECT name, sql FROM sqlite_master WHERE type='table'"))).fetchall()
                legacy = [
                    t_name for t_name, t_sql in tbl_rows
                    if t_sql and "UUID" in t_sql and t_name not in ("users", "alembic_version")
                ]
                if legacy:
                    _logging.getLogger("aidse").warning(
                        "Tables still using legacy UUID affinity: %s. They remain "
                        "readable; write a migration to convert them to CHAR(32).",
                        ", ".join(legacy),
                    )

                # No create_all here. It used to run on every start, which
                # meant a failed migration was invisible: the tables appeared
                # anyway, with no row in alembic_version, and the next real
                # migration had nothing to upgrade from. Every install ended up
                # in that state. If the schema is missing now, migrations
                # failed, and that should be loud rather than papered over.

                # Seed desktop local admin user if absent
                from apps.api.core.dependencies import DEFAULT_DESKTOP_USER_ID
                uid_hex = DEFAULT_DESKTOP_USER_ID.hex
                res = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": "local@aidse.internal"},
                )
                existing_row = res.scalar_one_or_none()
                if existing_row is None:
                    await conn.execute(
                        text(
                            "INSERT INTO users (id, email, password_hash, name, role, is_active, token_version) "
                            "VALUES (:id, :email, :password_hash, :name, :role, :is_active, :token_version)"
                        ),
                        {
                            "id": uid_hex,
                            "email": "local@aidse.internal",
                            "password_hash": "local_desktop_unrestricted_session",
                            "name": "AIDSE Analyst",
                            "role": "admin",
                            "is_active": 1,
                            "token_version": 1,
                        },
                    )
                elif existing_row != uid_hex:
                    await conn.execute(
                        text("UPDATE users SET id = :new_id WHERE email = :email"),
                        {"new_id": uid_hex, "email": "local@aidse.internal"},
                    )
    except Exception as exc:
        import logging
        logging.getLogger("aidse").error(f"Database startup/migration failed: {exc}")
        raise

    yield

    # Shutdown: dispose engine (clean connection pool)
    await engine.dispose()


def create_app() -> FastAPI:
    """
    FastAPI application factory.
    Returns a configured app instance ready to serve requests.
    """
    settings.enforce_production_safety()

    in_prod = settings.APP_ENV == "production"
    app = FastAPI(
        title="AIDSE Platform API",
        description=(
            "AI Data Scientist & AI Evaluation Platform — REST API. "
            "Section 11: API Design."
        ),
        version="0.1.0",
        # Interactive docs are a recon gift in production — disable there.
        docs_url=None if in_prod else "/api/docs",
        redoc_url=None if in_prod else "/api/redoc",
        openapi_url=None if in_prod else "/api/openapi.json",
        lifespan=lifespan,
    )

    # ── Host & Binding Guard (DNS Rebinding Prevention) ──────────────────────
    from apps.api.core.network import validate_host_binding
    validate_host_binding(settings.APP_HOST)

    @app.middleware("http")
    async def host_header_guard(request: Request, call_next):
        raw_host = request.headers.get("host", "")
        host_domain = raw_host.split(":")[0].strip().lower()
        if host_domain and host_domain not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "INVALID_HOST", "message": f"Host '{raw_host}' is forbidden."}},
            )
        return await call_next(request)

    # ── CORS (Section 8.2) ────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost)(:[0-9]+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Internal Session Token Middleware (Phase 3) ───────────────────────────
    from apps.api.core.token_middleware import InternalTokenMiddleware, warn_if_unprotected
    warn_if_unprotected()
    app.add_middleware(InternalTokenMiddleware)

    # ── Hardened Security Headers ─────────────────────────────────────────────
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


    # ── Rate limiting (Section 13.6) — brute-force protection on auth ────────
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from apps.api.core.rate_limit import limiter

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # AuthError exception handler
    from apps.api.modules.auth.service import AuthError
    from fastapi.responses import JSONResponse

    async def auth_error_handler(request: Request, exc: AuthError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "AUTH_ERROR", "message": str(exc)}},
        )

    app.add_exception_handler(AuthError, auth_error_handler)



    # ── Routers ───────────────────────────────────────────────────────────────
    from apps.api.modules.auth.router import router as auth_router
    from apps.api.modules.projects.router import router as projects_router
    from apps.api.modules.datasets.router import router as datasets_router
    from apps.api.modules.evaluation.router import router as evaluation_router
    from apps.api.modules.automl.router import router as automl_router
    from apps.api.modules.explainability.router import router as explainability_router
    from apps.api.modules.conversational.router import router as conversational_router
    from apps.api.modules.reporting.router import router as reporting_router
    from apps.api.modules.system.router import router as system_router

    # API Router setup
    api_router = APIRouter(prefix="/api/v1")
    api_router.include_router(auth_router)
    api_router.include_router(projects_router)
    api_router.include_router(datasets_router)
    api_router.include_router(evaluation_router)
    api_router.include_router(automl_router)
    api_router.include_router(explainability_router)
    api_router.include_router(conversational_router)
    api_router.include_router(reporting_router)
    api_router.include_router(system_router)

    app.include_router(api_router)

    # ── Health endpoint (must be registered before SPA catch-all route) ─────────
    @app.get("/health", tags=["System"], summary="Health check")
    async def health() -> dict:
        """Returns 200 OK when the service is running. Used by launcher and healthchecks."""
        return {"status": "ok", "version": "0.1.0"}

    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pathlib import Path
    import sys
    candidates = []
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        candidates.extend([
            exe_path.parents[2] / "apps" / "web" / "out",
            exe_path.parents[1] / "apps" / "web" / "out",
            exe_path.parent / "web" / "out",
        ])
    here = Path(__file__).resolve()
    candidates.extend([
        here.parents[1] / "web" / "out",
        here.parents[2] / "apps" / "web" / "out",
        here.parents[3] / "apps" / "web" / "out",
        here.parents[4] / "apps" / "web" / "out",
    ])

    out_dir = None
    for cand in candidates:
        if (cand / "index.html").is_file():
            out_dir = cand
            break

    if out_dir and out_dir.exists():
        next_static = out_dir / "_next"
        if next_static.exists():
            app.mount("/_next", StaticFiles(directory=str(next_static)), name="next_static")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            from fastapi import HTTPException
            import re
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)
            if not full_path or full_path == "/":
                return FileResponse(out_dir / "index.html")

            # Block directory traversal sequences
            normalized_parts = full_path.replace("\\", "/").split("/")
            if any(part in ("..", ".") for part in normalized_parts if part):
                raise HTTPException(status_code=403, detail="Access denied")

            # Path traversal prevention: enforce candidate is strictly inside out_dir
            try:
                candidate = (out_dir / full_path).resolve()
                if not candidate.is_relative_to(out_dir.resolve()):
                    raise HTTPException(status_code=403, detail="Access denied")
            except (ValueError, RuntimeError):
                raise HTTPException(status_code=403, detail="Access denied")

            if candidate.is_file():
                return FileResponse(candidate)
            html_file = (out_dir / f"{full_path}.html").resolve()
            if html_file.is_relative_to(out_dir.resolve()) and html_file.is_file():
                return FileResponse(html_file)
            index_in_dir = (out_dir / full_path / "index.html").resolve()
            if index_in_dir.is_relative_to(out_dir.resolve()) and index_in_dir.is_file():
                return FileResponse(index_in_dir)

            # ── Dynamic Route Rewriting for Next.js Static Export ──────────
            # Next.js builds dynamic [id] routes with a 'default' placeholder.
            # Handle both HTML page loads and .txt / index.txt RSC requests.
            is_txt = full_path.endswith(".txt")
            clean = full_path[:-4] if is_txt else full_path
            clean = clean.rstrip("/")
            if clean.endswith("/index"):
                clean = clean[:-6]
                is_txt = True

            parts = [p for p in clean.split("/") if p]
            current = out_dir
            resolved_parts = []
            for part in parts:
                if (current / part).is_dir():
                    current = current / part
                    resolved_parts.append(part)
                elif (current / "default").is_dir():
                    current = current / "default"
                    resolved_parts.append("default")
                else:
                    resolved_parts.append(part)
                    current = current / part

            target_dir = out_dir.joinpath(*resolved_parts)
            if is_txt:
                txt_cand = target_dir / "index.txt"
                if txt_cand.is_file():
                    return FileResponse(txt_cand)
                txt_cand2 = (out_dir / f"{'/'.join(resolved_parts)}.txt").resolve()
                if txt_cand2.is_file():
                    return FileResponse(txt_cand2)
            else:
                html_cand = target_dir / "index.html"
                if html_cand.is_file():
                    return FileResponse(html_cand)
                html_cand2 = (out_dir / f"{'/'.join(resolved_parts)}.html").resolve()
                if html_cand2.is_file():
                    return FileResponse(html_cand2)

            if (out_dir / "index.html").is_file():
                return FileResponse(out_dir / "index.html")
            raise HTTPException(status_code=404)

    return app


# Module-level app instance for uvicorn
app = create_app()
