"""Video tracking model."""

import enum
import uuid
from datetime import date

from sqlalchemy import JSON, Date, Enum, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class VideoStatus(str, enum.Enum):
    """Video generation status."""

    PENDING = "pending"
    GENERATING = "generating"
    UPLOADING = "uploading"
    PUBLISHED = "published"
    FAILED = "failed"


class Video(Base, TimestampMixin):
    """Track generated videos for digest stories."""

    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cluster_id: Mapped[str] = mapped_column(String(256), index=True)
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    rank: Mapped[int] = mapped_column(Integer)

    # Generation status
    status: Mapped[VideoStatus] = mapped_column(
        Enum(
            VideoStatus,
            values_callable=lambda e: [x.value for x in e],
            name="videostatus",
            create_type=False,
        ),
        default=VideoStatus.PENDING,
    )

    # Content
    script_json: Mapped[dict | None] = mapped_column(JSON)
    duration_seconds: Mapped[float | None] = mapped_column(Float)

    # File paths
    audio_path: Mapped[str | None] = mapped_column(String(512))
    video_path: Mapped[str | None] = mapped_column(String(512))
    s3_url: Mapped[str | None] = mapped_column(String(512))

    # YouTube metadata
    youtube_video_id: Mapped[str | None] = mapped_column(String(64))
    youtube_url: Mapped[str | None] = mapped_column(String(256))

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    def __repr__(self) -> str:
        return f"<Video {self.issue_date} rank={self.rank} status={self.status.value}>"
