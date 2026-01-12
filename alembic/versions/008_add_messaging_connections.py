"""Add messaging_connections table for Discord/Slack digest delivery

Revision ID: 008_add_messaging_connections
Revises: 007_change_author_to_text
Create Date: 2026-01-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_messaging_connections"
down_revision: str = "007_change_author_to_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messaging_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("platform", sa.String(20), nullable=False, index=True),
        sa.Column("platform_user_id", sa.String(50), nullable=False, index=True),
        sa.Column("platform_team_id", sa.String(50), nullable=True),
        sa.Column("platform_team_name", sa.String(255), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_unique_constraint(
        "uq_messaging_platform_user",
        "messaging_connections",
        ["platform", "platform_user_id"],
    )


def downgrade() -> None:
    op.drop_table("messaging_connections")
