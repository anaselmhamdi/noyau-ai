"""Add token tracking columns

Revision ID: 002_add_token_tracking
Revises: 001_initial
Create Date: 2026-01-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_token_tracking"
down_revision: str = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("cluster_summaries", sa.Column("prompt_tokens", sa.Integer(), nullable=True))
    op.add_column("cluster_summaries", sa.Column("completion_tokens", sa.Integer(), nullable=True))
    op.add_column("cluster_summaries", sa.Column("total_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("cluster_summaries", "total_tokens")
    op.drop_column("cluster_summaries", "completion_tokens")
    op.drop_column("cluster_summaries", "prompt_tokens")
