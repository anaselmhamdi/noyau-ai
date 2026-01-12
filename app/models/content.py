import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Enum, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ContentSource(str, enum.Enum):
    """Supported content sources."""

    X = "x"
    REDDIT = "reddit"
    GITHUB = "github"
    YOUTUBE = "youtube"
    DEVTO = "devto"
    RSS = "rss"
    STATUS = "status"
    BLUESKY = "bluesky"


class ContentItem(Base):
    """Ingested content item from any source."""

    __tablename__ = "content_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[ContentSource] = mapped_column(
        Enum(
            ContentSource,
            values_callable=lambda e: [x.value for x in e],
            name="contentsource",
            create_type=False,
        ),
        index=True,
    )
    source_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime] = mapped_column(index=True)
    fetched_at: Mapped[datetime] = mapped_column(default=func.now())
    text: Mapped[str | None] = mapped_column(Text)
    raw_json_ref: Mapped[str | None] = mapped_column(String(500))

    # Relationships
    metrics_snapshots: Mapped[list["MetricsSnapshot"]] = relationship(
        back_populates="item", order_by="MetricsSnapshot.captured_at"
    )
    cluster_items: Mapped[list["ClusterItem"]] = relationship("ClusterItem", back_populates="item")

    def __repr__(self) -> str:
        return f"<ContentItem {self.source.value}: {self.title[:50]}>"


class MetricsSnapshot(Base):
    """Point-in-time metrics for a content item."""

    __tablename__ = "metrics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_items.id", ondelete="CASCADE"), index=True
    )
    captured_at: Mapped[datetime] = mapped_column(default=func.now(), index=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Relationships
    item: Mapped["ContentItem"] = relationship(back_populates="metrics_snapshots")

    def __repr__(self) -> str:
        return f"<MetricsSnapshot {self.item_id} @ {self.captured_at}>"


# Import ClusterItem here to avoid circular import issues
from app.models.cluster import ClusterItem  # noqa: E402, F401
