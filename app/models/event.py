import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Event(Base):
    """Analytics event for tracking user interactions."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event_name: Mapped[str] = mapped_column(String(100), index=True)
    ts: Mapped[datetime] = mapped_column(default=func.now(), index=True)
    properties_json: Mapped[dict | None] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<Event {self.event_name} @ {self.ts}>"
