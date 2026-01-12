"""Add digest_deliveries table for per-user timezone delivery tracking

Revision ID: 009_add_digest_deliveries
Revises: 008_add_messaging_connections
Create Date: 2026-01-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_digest_deliveries"
down_revision: str = "008_add_messaging_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "digest_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("issue_date", sa.Date(), nullable=False, index=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=False),
    )

    op.create_unique_constraint(
        "uq_user_issue_date",
        "digest_deliveries",
        ["user_id", "issue_date"],
    )


def downgrade() -> None:
    op.drop_table("digest_deliveries")
