"""
Shared utilities for job modules.

Common functions used by video_generate.py and podcast_generate.py.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cluster import Cluster, ClusterSummary
from app.schemas.common import Citation
from app.schemas.llm import ClusterDistillOutput


def summary_to_distill_output(summary: ClusterSummary) -> ClusterDistillOutput:
    """Convert a ClusterSummary to ClusterDistillOutput for media generation."""
    citations = [
        Citation(url=c.get("url", ""), label=c.get("label", "Source"))
        for c in (summary.citations_json or [])
    ]
    if not citations:
        citations = [Citation(url="https://noyau.news", label="Noyau News")]

    bullets = summary.bullets_json or []
    if len(bullets) < 2:
        bullets = bullets + ["See full story for details."] * (2 - len(bullets))
    elif len(bullets) > 2:
        bullets = bullets[:2]

    return ClusterDistillOutput(
        headline=summary.headline,
        teaser=summary.teaser,
        takeaway=summary.takeaway,
        why_care=summary.why_care,
        bullets=bullets,
        citations=citations,
        confidence=summary.confidence.value,
    )


async def get_clusters_for_date(db: AsyncSession, issue_date: date) -> list[Cluster]:
    """Query clusters with summaries for the given date."""
    stmt = (
        select(Cluster)
        .options(selectinload(Cluster.summary))
        .where(Cluster.issue_date == issue_date)
        .order_by(Cluster.cluster_score.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def determine_topic(cluster: Cluster) -> str:
    """Determine media topic from cluster."""
    if cluster.dominant_topic:
        topic = cluster.dominant_topic.value
        if topic in ("security",):
            return "security"
        elif topic in ("oss",):
            return "oss"
        elif topic in ("macro", "deepdive"):
            return "ai"
    return "general"
