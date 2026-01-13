"""Add podcast fields to issues table

Revision ID: 010_add_podcast_to_issues
Revises: f58b43023b1d
Create Date: 2026-01-13

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_add_podcast_to_issues"
down_revision: str = "f58b43023b1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "issues",
        sa.Column("podcast_audio_url", sa.String(512), nullable=True),
    )
    op.add_column(
        "issues",
        sa.Column("podcast_youtube_url", sa.String(255), nullable=True),
    )
    op.add_column(
        "issues",
        sa.Column("podcast_duration_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("issues", "podcast_duration_seconds")
    op.drop_column("issues", "podcast_youtube_url")
    op.drop_column("issues", "podcast_audio_url")
