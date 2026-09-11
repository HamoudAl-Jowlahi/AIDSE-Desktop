"""dataset version lineage + transformation history

Revision ID: d2c8a5e91f04
Revises: b4f9d21c7e55
Create Date: 2026-08-25

Phase 5 — Data Preparation Workbench: tracks parent versions and the
ordered list of transformation steps used to derive each new version.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2c8a5e91f04"
down_revision: Union[str, None] = "b4f9d21c7e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_versions",
        sa.Column("parent_version_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "dataset_versions",
        sa.Column("transformation_history", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_versions", "transformation_history")
    op.drop_column("dataset_versions", "parent_version_id")
