"""add profile_status to dataset_versions

Revision ID: b4f9d21c7e55
Revises: c7c17ae19a38
Create Date: 2026-08-25

Phase 2 — Dataset Ingestion: tracks whether a version's profile is
pending / ready / failed so large-file profiling can run asynchronously.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4f9d21c7e55"
down_revision: Union[str, None] = "c7c17ae19a38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_versions",
        sa.Column("profile_status", sa.String(length=20), nullable=True),
    )
    # Existing rows already carry profile_data (or failed silently before);
    # mark them ready so the UI does not show them as pending.
    op.execute(
        "UPDATE dataset_versions SET profile_status = 'ready' WHERE profile_data IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("dataset_versions", "profile_status")
