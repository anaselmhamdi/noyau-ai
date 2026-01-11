"""Add is_subscribed column to users for email subscription management

Revision ID: 006_add_user_is_subscribed
Revises: 005_add_first_published_at
Create Date: 2026-01-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006_add_user_is_subscribed"
down_revision: str = "005_add_first_published_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("is_subscribed", sa.Boolean(), nullable=False, server_default="true")
    )


def downgrade() -> None:
    op.drop_column("users", "is_subscribed")
