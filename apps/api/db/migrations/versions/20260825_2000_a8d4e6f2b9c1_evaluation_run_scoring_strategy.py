"""evaluation run scoring strategy columns

Revision ID: a8d4e6f2b9c1
Revises: f7a9c4d1e2b3
Create Date: 2026-08-25

Phase 13 — AI Evaluation: persists how each run's outputs were graded.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8d4e6f2b9c1"
down_revision: Union[str, None] = "f7a9c4d1e2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("evaluation_runs", sa.Column("scoring_strategy", sa.String(length=30), nullable=True))
    op.add_column("evaluation_runs", sa.Column("scoring_params", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluation_runs", "scoring_params")
    op.drop_column("evaluation_runs", "scoring_strategy")
