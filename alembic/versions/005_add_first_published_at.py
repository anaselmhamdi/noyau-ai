"""Add first_published_at column to clusters for deduplication tracking

Revision ID: 005_add_first_published_at
Revises: 004_add_job_runs
Create Date: 2026-01-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_add_first_published_at"
down_revision: str = "004_add_job_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clusters", sa.Column("first_published_at", sa.Date(), nullable=True))
    op.create_index("ix_clusters_first_published_at", "clusters", ["first_published_at"])


def downgrade() -> None:
    op.drop_index("ix_clusters_first_published_at", table_name="clusters")
    op.drop_column("clusters", "first_published_at")
