"""Digest delivery tracking for per-user timezone support."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class DigestDelivery(Base):
    """Tracks which users have received the digest for a given issue date.

    Prevents duplicate sends and enables catch-up logic for users
    who missed their delivery window.
    """

    __tablename__ = "digest_deliveries"
    __table_args__ = (UniqueConstraint("user_id", "issue_date", name="uq_user_issue_date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    delivered_at: Mapped[datetime] = mapped_column()

    # Relationships
    user: Mapped[User] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<DigestDelivery user={self.user_id} date={self.issue_date}>"
