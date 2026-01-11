"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-01-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enums with conditional check (Postgres doesn't support IF NOT EXISTS for TYPE)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE contentsource AS ENUM ('x', 'reddit', 'github', 'youtube', 'devto', 'rss', 'status');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE dominanttopic AS ENUM ('macro', 'oss', 'security', 'dev', 'deepdive', 'sauce');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE confidencelevel AS ENUM ('low', 'medium', 'high');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Reference enums without auto-creating them
    content_source_enum = postgresql.ENUM(
        "x",
        "reddit",
        "github",
        "youtube",
        "devto",
        "rss",
        "status",
        name="contentsource",
        create_type=False,
    )
    dominant_topic_enum = postgresql.ENUM(
        "macro",
        "oss",
        "security",
        "dev",
        "deepdive",
        "sauce",
        name="dominanttopic",
        create_type=False,
    )
    confidence_level_enum = postgresql.ENUM(
        "low",
        "medium",
        "high",
        name="confidencelevel",
        create_type=False,
    )

    # Users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("timezone", sa.String(50), nullable=False, default="Europe/Paris"),
        sa.Column("delivery_time_local", sa.String(5), nullable=False, default="08:00"),
        sa.Column("ref_code", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Magic links table
    op.create_table(
        "magic_links",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, index=True),
        sa.Column("redirect_path", sa.String(255), nullable=False, default="/"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Content items table
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", content_source_enum, nullable=False, index=True),
        sa.Column("source_id", sa.String(255), nullable=True),
        sa.Column("url", sa.String(2048), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=False, index=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("raw_json_ref", sa.String(500), nullable=True),
    )

    # Metrics snapshots table
    op.create_table(
        "metrics_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "captured_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True
        ),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False, default={}),
    )

    # Clusters table
    op.create_table(
        "clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("issue_date", sa.Date(), nullable=False, index=True),
        sa.Column("canonical_identity", sa.String(2048), nullable=False, index=True),
        sa.Column("dominant_topic", dominant_topic_enum, nullable=True),
        sa.Column("cluster_score", sa.Float(), nullable=False, default=0.0),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Cluster items (many-to-many)
    op.create_table(
        "cluster_items",
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clusters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("rank_in_cluster", sa.Integer(), nullable=False, default=0),
    )

    # Cluster summaries table
    op.create_table(
        "cluster_summaries",
        sa.Column(
            "cluster_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clusters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("headline", sa.String(200), nullable=False),
        sa.Column("teaser", sa.String(500), nullable=False),
        sa.Column("takeaway", sa.Text(), nullable=False),
        sa.Column("why_care", sa.Text(), nullable=True),
        sa.Column("bullets_json", postgresql.JSONB(), nullable=False, default=[]),
        sa.Column("citations_json", postgresql.JSONB(), nullable=False, default=[]),
        sa.Column("confidence", confidence_level_enum, nullable=False, default="medium"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Issues table
    op.create_table(
        "issues",
        sa.Column("issue_date", sa.Date(), primary_key=True),
        sa.Column("public_url", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Events table
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("event_name", sa.String(100), nullable=False, index=True),
        sa.Column("ts", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column("properties_json", postgresql.JSONB(), nullable=True, default={}),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("issues")
    op.drop_table("cluster_summaries")
    op.drop_table("cluster_items")
    op.drop_table("clusters")
    op.drop_table("metrics_snapshots")
    op.drop_table("content_items")
    op.drop_table("sessions")
    op.drop_table("magic_links")
    op.drop_table("users")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS confidencelevel")
    op.execute("DROP TYPE IF EXISTS dominanttopic")
    op.execute("DROP TYPE IF EXISTS contentsource")
