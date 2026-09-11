"""
Alembic migration environment for AIDSE Platform.
Section 23.2 Rule 6: All schema changes go through Alembic — never direct DDL.

Configured for async SQLAlchemy (asyncpg) per ADR-002.
DATABASE_URL is read from the environment, not hardcoded.
"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from dotenv import load_dotenv

load_dotenv()

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import all models so Alembic can detect them for autogenerate
from apps.api.db.base import Base  # noqa: F401 — must be imported before models

from apps.api.modules.auth.models import User  # noqa: F401
from apps.api.modules.projects.models import AuditLog, Project, ProjectMember  # noqa: F401
from apps.api.modules.datasets.models import Dataset, DatasetVersion, GoldenDataset, GoldenCase  # noqa: F401
from apps.api.modules.evaluation.models import EvaluationRun, EvaluationResult, RegressionReport, RegressionReportCase, ScheduledEvaluation  # noqa: F401
from apps.api.modules.automl.models import Experiment, ModelTrial  # noqa: F401

# Alembic Config object
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use metadata from all imported models
target_metadata = Base.metadata

# Override sqlalchemy.url with the DATABASE_URL environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://aidse:aidse_dev_password@localhost:5432/aidse",
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without DB connection)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # noqa: ANN001
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with an async engine."""
    connectable = create_async_engine(DATABASE_URL)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
