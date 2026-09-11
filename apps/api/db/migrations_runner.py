"""
AIDSE Platform — Headless Alembic Migration Runner
Section 5: Database Migrations & First-Run Experience

Brings the database to 'head' on startup, without CLI interaction.

Three cases have to work, because installations in the wild are in all three:

  1. Empty database         → upgrade head builds everything.
  2. Already under Alembic  → upgrade head applies what is outstanding.
  3. Tables but no version  → the schema came from Base.metadata.create_all
                              while this runner was silently failing (it
                              computed the repo root one directory too low and
                              returned without finding alembic.ini). Those
                              databases match head exactly — verified by
                              building both ways and diffing — so they are
                              stamped, then upgraded.

Case 3 is the upgrade path for every existing install. Without it, a corrected
runner would try to CREATE TABLE over live tables and fail on every launch.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from apps.api.core.config import get_settings

logger = logging.getLogger("aidse.migrations")

# The single source of truth for migrations. apps/api/alembic/ was a second,
# orphaned tree (one root revision, never referenced) and has been removed.
_SCRIPT_LOCATION = ("apps", "api", "db", "migrations")


def _repo_root() -> Path:
    """This file is <root>/apps/api/db/migrations_runner.py."""
    return Path(__file__).resolve().parents[3]


def _sync_url(database_url: str) -> str:
    """Alembic's env.py drives async engines, but the inspection below is sync."""
    return database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


def _build_config(root: Path) -> Config | None:
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        logger.warning("alembic.ini not found at %s; skipping migrations.", ini_path)
        return None

    script_dir = root.joinpath(*_SCRIPT_LOCATION)
    if not script_dir.is_dir():
        logger.warning("Migration scripts not found at %s; skipping migrations.", script_dir)
        return None

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(script_dir))
    return cfg


def _needs_stamp(database_url: str) -> bool:
    """True when the schema exists but Alembic has never recorded a revision."""
    try:
        engine = create_engine(_sync_url(database_url))
        try:
            tables = set(inspect(engine).get_table_names())
            recorded = None
            if "alembic_version" in tables:
                with engine.connect() as conn:
                    recorded = conn.execute(
                        text("SELECT version_num FROM alembic_version")
                    ).scalar()
        finally:
            engine.dispose()
    except Exception as exc:
        logger.warning("Could not inspect the database before migrating: %s", exc)
        return False

    # An alembic_version table with no row means no revision is recorded, which
    # is the same situation as having no table at all.
    if recorded:
        return False

    # Ignore an empty database — upgrade head handles that case properly.
    return bool(tables - {"alembic_version"})


def run_migrations_headless() -> None:
    """Bring the database to 'head'. Logs and returns on failure, never raises."""
    root = _repo_root()
    cfg = _build_config(root)
    if cfg is None:
        return

    database_url = get_settings().DATABASE_URL

    try:
        if _needs_stamp(database_url):
            logger.info(
                "Database has tables but no Alembic revision — stamping it at "
                "head before upgrading (schema was created by create_all)."
            )
            command.stamp(cfg, "head")

        command.upgrade(cfg, "head")
        logger.info("Database migrations are at head.")
    except Exception as exc:
        logger.error("Headless migration failed: %s", exc)
