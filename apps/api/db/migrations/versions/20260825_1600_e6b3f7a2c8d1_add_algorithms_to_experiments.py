"""add algorithms to experiments

Revision ID: e6b3f7a2c8d1
Revises: d2c8a5e91f04
Create Date: 2026-08-25

Phase 8 — ML Lab: persists the user-selected focused model set per
experiment. NULL keeps task-appropriate defaults.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6b3f7a2c8d1"
down_revision: Union[str, None] = "d2c8a5e91f04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("experiments", sa.Column("algorithms", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("experiments", "algorithms")
