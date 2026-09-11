"""
AIDSE Platform — Headless Alembic Migration Runner
Section 5: Database Migrations & First-Run Experience

Executes Alembic migrations automatically and programmatically on app launch,
ensuring the SQLite database schema reaches 'head' headlessly in the background.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path

from alembic.config import Config
from alembic import command

logger = logging.getLogger("aidse.migrations")


def run_migrations_headless() -> None:
    """
    Programmatically run Alembic migrations to 'head' on startup.
    Runs silently in background thread without CLI user interaction.
    """
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini_path = repo_root / "alembic.ini"
    if not alembic_ini_path.exists():
        alembic_ini_path = repo_root / "apps" / "api" / "alembic.ini"

    if not alembic_ini_path.exists():
        logger.warning("alembic.ini not found, skipping headless migration execution")
        return

    try:
        alembic_cfg = Config(str(alembic_ini_path))
        # Ensure script_location points to valid directory
        script_dir = repo_root / "apps" / "api" / "db" / "migrations"
        if not script_dir.exists():
            script_dir = repo_root / "apps" / "api" / "alembic"

        if script_dir.exists():
            alembic_cfg.set_main_option("script_location", str(script_dir))

        command.upgrade(alembic_cfg, "head")
        logger.info("Headless Alembic database migrations completed successfully to 'head'.")
    except Exception as exc:
        logger.error(f"Headless migration failed: {exc}")
        # In test environments or when tables exist, log warning rather than crashing
