"""Job execution history model."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class JobRun(Base):
    """Records each execution of a scheduled job."""

    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(String(100), index=True)
    scheduled_at: Mapped[datetime]
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime]
    outcome: Mapped[str] = mapped_column(String(20))  # success, error, missed, skipped
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
