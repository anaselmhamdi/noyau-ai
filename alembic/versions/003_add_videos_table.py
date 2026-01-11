"""Add videos table

Revision ID: 003_add_videos
Revises: 002_add_token_tracking
Create Date: 2026-01-11

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_videos"
down_revision: str = "002_add_token_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Use DO block to handle "IF NOT EXISTS" for enum types (PostgreSQL < 9.1 compatibility)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE videostatus AS ENUM ('pending', 'generating', 'uploading', 'published', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Use postgresql.ENUM with create_type=False to avoid auto-creation
    from sqlalchemy.dialects import postgresql

    videostatus_enum = postgresql.ENUM(
        "pending",
        "generating",
        "uploading",
        "published",
        "failed",
        name="videostatus",
        create_type=False,
    )

    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cluster_id", sa.String(256), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", videostatus_enum, nullable=False),
        sa.Column("script_json", sa.JSON(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("audio_path", sa.String(512), nullable=True),
        sa.Column("video_path", sa.String(512), nullable=True),
        sa.Column("s3_url", sa.String(512), nullable=True),
        sa.Column("youtube_video_id", sa.String(64), nullable=True),
        sa.Column("youtube_url", sa.String(256), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_videos_issue_date", "videos", ["issue_date"])
    op.create_index("ix_videos_cluster_id", "videos", ["cluster_id"])


def downgrade() -> None:
    op.drop_index("ix_videos_cluster_id", table_name="videos")
    op.drop_index("ix_videos_issue_date", table_name="videos")
    op.drop_table("videos")
    op.execute("DROP TYPE videostatus")
