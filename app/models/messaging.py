"""Messaging platform connections for digest delivery (Discord, Slack)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class MessagingConnection(Base, TimestampMixin):
    """Connection to a messaging platform (Discord, Slack) for a user.

    Used to deliver daily digest DMs to users who subscribe via these platforms.
    """

    __tablename__ = "messaging_connections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # Platform info
    platform: Mapped[str] = mapped_column(String(20), index=True)  # 'discord' or 'slack'
    platform_user_id: Mapped[str] = mapped_column(String(50), index=True)
    platform_team_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    platform_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # OAuth token (for Slack; Discord bot uses global token)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Connection state
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(default=None)

    # Relationships
    user: Mapped[User] = relationship(back_populates="messaging_connections", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_messaging_platform_user"),
    )

    def __repr__(self) -> str:
        return f"<MessagingConnection {self.platform}:{self.platform_user_id}>"
