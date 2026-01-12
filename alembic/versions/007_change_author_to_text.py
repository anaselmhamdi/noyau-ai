"""Change author column from VARCHAR(255) to TEXT

Revision ID: 007_change_author_to_text
Revises: 006_add_user_is_subscribed
Create Date: 2026-01-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007_change_author_to_text"
down_revision: str = "006_add_user_is_subscribed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "content_items",
        "author",
        type_=sa.Text(),
        existing_type=sa.String(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "content_items",
        "author",
        type_=sa.String(255),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
