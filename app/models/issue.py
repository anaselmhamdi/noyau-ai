from datetime import date, datetime

from sqlalchemy import Date, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Issue(Base):
    """A daily digest issue containing top 10 clusters."""

    __tablename__ = "issues"

    issue_date: Mapped[date] = mapped_column(Date, primary_key=True)
    public_url: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Podcast fields
    podcast_audio_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    podcast_youtube_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    podcast_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Issue {self.issue_date}>"

    @property
    def has_podcast(self) -> bool:
        """Check if this issue has an associated podcast."""
        return self.podcast_audio_url is not None
