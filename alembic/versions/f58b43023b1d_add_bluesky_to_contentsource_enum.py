"""add bluesky to contentsource enum

Revision ID: f58b43023b1d
Revises: 009_add_digest_deliveries
Create Date: 2026-01-13 11:12:05.627200

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f58b43023b1d"
down_revision: str | None = "009_add_digest_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add 'bluesky' to the contentsource enum
    op.execute("ALTER TYPE contentsource ADD VALUE IF NOT EXISTS 'bluesky'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values easily
    # This would require recreating the enum and all dependent columns
    pass
