from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.messaging import MessagingConnection


class User(Base, TimestampMixin):
    """User account for email subscribers."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Paris")
    delivery_time_local: Mapped[str] = mapped_column(String(5), default="08:00")
    ref_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    sessions: Mapped[list[Session]] = relationship(back_populates="user", lazy="selectin")
    messaging_connections: Mapped[list[MessagingConnection]] = relationship(
        back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class MagicLink(Base):
    """Magic link tokens for passwordless authentication."""

    __tablename__ = "magic_links"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    redirect_path: Mapped[str] = mapped_column(String(255), default="/")
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    def __repr__(self) -> str:
        return f"<MagicLink for {self.email}>"


class Session(Base, TimestampMixin):
    """User session for cookie-based authentication."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column()

    # Relationships
    user: Mapped[User] = relationship(back_populates="sessions", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Session {self.id}>"
