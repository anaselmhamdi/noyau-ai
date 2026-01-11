import enum
import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, Enum, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class DominantTopic(str, enum.Enum):
    """Topic categories for clusters."""

    MACRO = "macro"
    OSS = "oss"
    SECURITY = "security"
    DEV = "dev"
    DEEPDIVE = "deepdive"
    SAUCE = "sauce"


class ConfidenceLevel(str, enum.Enum):
    """LLM confidence levels for summaries."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Cluster(Base, TimestampMixin):
    """A cluster of related content items for a given day."""

    __tablename__ = "clusters"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    canonical_identity: Mapped[str] = mapped_column(String(2048), index=True)
    dominant_topic: Mapped[DominantTopic | None] = mapped_column(
        Enum(
            DominantTopic,
            values_callable=lambda e: [x.value for x in e],
            name="dominanttopic",
            create_type=False,
        )
    )
    cluster_score: Mapped[float] = mapped_column(Float, default=0.0)
    first_published_at: Mapped[date | None] = mapped_column(Date, index=True, default=None)

    # Relationships
    items: Mapped[list["ClusterItem"]] = relationship(
        back_populates="cluster", cascade="all, delete-orphan"
    )
    summary: Mapped["ClusterSummary | None"] = relationship(
        back_populates="cluster", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Cluster {self.issue_date}: {self.canonical_identity[:50]}>"


class ClusterItem(Base):
    """Many-to-many relationship between clusters and content items."""

    __tablename__ = "cluster_items"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("clusters.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("content_items.id", ondelete="CASCADE"), primary_key=True
    )
    rank_in_cluster: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    cluster: Mapped["Cluster"] = relationship(back_populates="items")
    item: Mapped["ContentItem"] = relationship("ContentItem", back_populates="cluster_items")

    def __repr__(self) -> str:
        return f"<ClusterItem cluster={self.cluster_id} item={self.item_id}>"


class ClusterSummary(Base):
    """LLM-generated summary for a cluster."""

    __tablename__ = "cluster_summaries"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("clusters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    headline: Mapped[str] = mapped_column(String(200))
    teaser: Mapped[str] = mapped_column(String(500))
    takeaway: Mapped[str] = mapped_column(Text)
    why_care: Mapped[str | None] = mapped_column(Text)
    bullets_json: Mapped[list] = mapped_column(JSON, default=list)
    citations_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        Enum(
            ConfidenceLevel,
            values_callable=lambda e: [x.value for x in e],
            name="confidencelevel",
            create_type=False,
        ),
        default=ConfidenceLevel.MEDIUM,
    )
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=func.now())

    # Relationships
    cluster: Mapped["Cluster"] = relationship(back_populates="summary")

    def __repr__(self) -> str:
        return f"<ClusterSummary {self.headline[:50]}>"


# Forward reference for ContentItem
from app.models.content import ContentItem  # noqa: E402, F401
