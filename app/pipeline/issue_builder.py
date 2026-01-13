import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_config, get_settings
from app.core.datetime_utils import get_cutoff
from app.core.logging import get_logger
from app.models.cluster import Cluster, ClusterItem, ClusterSummary, ConfidenceLevel
from app.models.content import ContentItem, ContentSource
from app.models.issue import Issue
from app.pipeline.clustering import build_clusters_for_date
from app.pipeline.distiller import distill_top_clusters
from app.pipeline.filters import filter_political_clusters
from app.pipeline.scoring import ClusterScorer, HistoricalMetrics, rank_clusters
from app.pipeline.topics import detect_topic_from_identity, topic_to_dominant_topic
from app.schemas.llm import DistillResult

logger = get_logger(__name__)


async def get_items_for_window(
    db: AsyncSession,
    window_hours: int = 36,
) -> list[ContentItem]:
    """
    Get content items from the time window.

    Args:
        db: Database session
        window_hours: Hours to look back (default 36 for overlap)

    Returns:
        List of content items with metrics snapshots
    """
    cutoff = get_cutoff(hours=window_hours)

    result = await db.execute(
        select(ContentItem)
        .options(selectinload(ContentItem.metrics_snapshots))
        .where(ContentItem.published_at >= cutoff)
        .order_by(ContentItem.published_at.desc())
    )

    items = list(result.scalars().all())
    logger.bind(count=len(items), window_hours=window_hours).info("items_loaded")
    return items


async def get_social_items(
    db: AsyncSession,
    hours: int = 24,
) -> list[ContentItem]:
    """Get X/Twitter and Bluesky items for echo detection."""
    cutoff = get_cutoff(hours=hours)

    result = await db.execute(
        select(ContentItem)
        .where(ContentItem.source.in_([ContentSource.X, ContentSource.BLUESKY]))
        .where(ContentItem.published_at >= cutoff)
    )

    return list(result.scalars().all())


async def get_all_published_clusters(
    db: AsyncSession,
) -> set[str]:
    """Get canonical identities from all previously published issues."""
    result = await db.execute(
        select(Cluster.canonical_identity).where(Cluster.first_published_at.isnot(None))
    )

    return set(result.scalars().all())


async def get_missed_from_yesterday(
    db: AsyncSession,
    limit: int = 3,
) -> list[Cluster]:
    """Get top clusters from yesterday for 'You may have missed' section."""
    yesterday = date.today() - timedelta(days=1)

    result = await db.execute(
        select(Cluster)
        .options(selectinload(Cluster.summary))
        .where(Cluster.issue_date == yesterday)
        .order_by(Cluster.cluster_score.desc())
        .limit(limit)
    )

    return list(result.scalars().all())


async def build_historical_metrics(
    db: AsyncSession,
    days: int = 7,
) -> HistoricalMetrics:
    """Build historical metrics for percentile calculations."""
    historical = HistoricalMetrics()
    cutoff = get_cutoff(days=days)

    # Get items with snapshots for each source
    for source in ContentSource:
        result = await db.execute(
            select(ContentItem)
            .options(selectinload(ContentItem.metrics_snapshots))
            .where(ContentItem.source == source)
            .where(ContentItem.fetched_at >= cutoff)
            .limit(1000)
        )
        items = result.scalars().all()

        # Calculate engagement values
        engagements = []
        for item in items:
            if item.metrics_snapshots:
                latest = item.metrics_snapshots[-1]
                metrics = latest.metrics_json

                if source == ContentSource.X:
                    eng = (
                        metrics.get("likes", 0)
                        + 2 * metrics.get("retweets", 0)
                        + metrics.get("replies", 0)
                    )
                elif source == ContentSource.REDDIT:
                    eng = metrics.get("upvotes", 0) + 2 * metrics.get("comments", 0)
                elif source == ContentSource.YOUTUBE:
                    eng = metrics.get("views", 0) / 1000 + 2 * metrics.get("comments", 0)
                elif source == ContentSource.GITHUB:
                    eng = metrics.get("stars", 0) + metrics.get("forks", 0)
                elif source == ContentSource.DEVTO:
                    eng = metrics.get("reactions", 0) + 2 * metrics.get("comments", 0)
                elif source == ContentSource.BLUESKY:
                    eng = (
                        metrics.get("likes", 0)
                        + 2 * metrics.get("reposts", 0)
                        + metrics.get("replies", 0)
                    )
                else:
                    eng = 0.0

                engagements.append(eng)

        if engagements:
            historical.add_distribution(source.value, engagements)

    return historical


async def save_issue_to_db(
    db: AsyncSession,
    issue_date: date,
    ranked_with_summaries: list[
        tuple[str, list[ContentItem], dict[str, Any], DistillResult | None]
    ],
) -> Issue:
    """Save the issue and clusters to the database."""
    settings = get_settings()

    # Create issue
    issue = Issue(
        issue_date=issue_date,
        public_url=f"{settings.base_url}/daily/{issue_date}",
    )
    db.add(issue)

    # Create clusters and summaries
    for identity, items, score_info, summary in ranked_with_summaries:
        # Determine dominant topic
        topic_str = detect_topic_from_identity(identity, score_info.get("is_viral", False))
        topic = topic_to_dominant_topic(topic_str)

        cluster = Cluster(
            issue_date=issue_date,
            canonical_identity=identity,
            dominant_topic=topic,
            cluster_score=score_info["score"],
            first_published_at=issue_date,
        )
        db.add(cluster)
        await db.flush()

        # Add cluster items
        for rank, item in enumerate(items):
            cluster_item = ClusterItem(
                cluster_id=cluster.id,
                item_id=item.id,
                rank_in_cluster=rank,
            )
            db.add(cluster_item)

        # Add summary if available (summary is a DistillResult with output + token usage)
        if summary:
            conf_map = {
                "low": ConfidenceLevel.LOW,
                "medium": ConfidenceLevel.MEDIUM,
                "high": ConfidenceLevel.HIGH,
            }
            output = summary.output

            cluster_summary = ClusterSummary(
                cluster_id=cluster.id,
                headline=output.headline,
                teaser=output.teaser,
                takeaway=output.takeaway,
                why_care=output.why_care,
                bullets_json=output.bullets,
                citations_json=[c.model_dump() for c in output.citations],
                confidence=conf_map.get(output.confidence, ConfidenceLevel.MEDIUM),
                prompt_tokens=summary.prompt_tokens,
                completion_tokens=summary.completion_tokens,
                total_tokens=summary.total_tokens,
            )
            db.add(cluster_summary)

    await db.commit()
    logger.bind(date=str(issue_date)).info("issue_saved_to_db")
    return issue


def write_public_json(
    issue_date: date,
    ranked_with_summaries: list[
        tuple[str, list[ContentItem], dict[str, Any], DistillResult | None]
    ],
    output_dir: str = "public/issues",
) -> Path:
    """
    Write public JSON file for static site generation.

    Args:
        issue_date: Date of the issue
        ranked_with_summaries: Scored and distilled clusters
        output_dir: Output directory

    Returns:
        Path to the written JSON file
    """
    config = get_config()

    items = []
    for rank, (identity, content_items, score_info, summary) in enumerate(
        ranked_with_summaries, start=1
    ):
        if summary:
            output = summary.output
            item_data = {
                "rank": rank,
                "headline": output.headline,
                "teaser": output.teaser,
                "locked": rank > config.digest.free_items,
            }

            # Only include full data for unlocked items
            if rank <= config.digest.free_items:
                item_data.update(
                    {
                        "takeaway": output.takeaway,
                        "why_care": output.why_care,
                        "bullets": output.bullets,
                        "citations": [c.model_dump() for c in output.citations],
                        "confidence": output.confidence,
                    }
                )

            items.append(item_data)

    output_data = {
        "date": str(issue_date),
        "items": items,
    }

    # Write to file
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_path = output_path / f"{issue_date}.json"

    with open(file_path, "w") as f:
        json.dump(output_data, f, indent=2)

    logger.bind(path=str(file_path)).info("public_json_written")
    return file_path


async def build_daily_issue(
    db: AsyncSession,
    issue_date: date | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Build the daily issue.

    Main orchestrator for the daily pipeline:
    1. Load items from time window
    2. Filter political content
    3. Build clusters
    4. Score and rank clusters
    5. Distill top 10 with LLM
    6. Save to database (skipped if dry_run)
    7. Write public JSON (skipped if dry_run)

    Args:
        db: Database session
        issue_date: Date for the issue (defaults to today)
        dry_run: If True, skip persistence (DB save and JSON write)

    Returns:
        Dict with stats about the build. If dry_run=True, also includes
        'ranked_with_summaries' for preview purposes.
    """
    if issue_date is None:
        issue_date = date.today()

    config = get_config()
    settings = get_settings()

    logger.bind(date=str(issue_date)).info("daily_issue_build_started")

    stats = {
        "date": str(issue_date),
        "items_loaded": 0,
        "clusters_built": 0,
        "clusters_after_filter": 0,
        "top_clusters": 0,
        "summaries_generated": 0,
    }

    # Step 1: Load items
    items = await get_items_for_window(db)
    stats["items_loaded"] = len(items)

    if not items:
        logger.warning("no_items_found")
        return stats

    # Step 2: Build clusters
    clusters = build_clusters_for_date(items, issue_date)
    stats["clusters_built"] = len(clusters)

    # Step 3: Filter political content
    openai_client = None
    if settings.openai_api_key:
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    clusters = await filter_political_clusters(clusters, openai_client)
    stats["clusters_after_filter"] = len(clusters)

    # Step 4: Build scorer with historical data
    historical = await build_historical_metrics(db)
    social_items = await get_social_items(db)
    published_clusters = await get_all_published_clusters(db)

    # Hard exclusion: filter out clusters that were already published
    clusters_before_exclusion = len(clusters)
    clusters = {
        identity: items
        for identity, items in clusters.items()
        if identity not in published_clusters
    }
    logger.bind(
        before=clusters_before_exclusion,
        after=len(clusters),
        excluded=clusters_before_exclusion - len(clusters),
    ).info("clusters_hard_exclusion_applied")

    scorer = ClusterScorer(
        config=config,
        historical=historical,
        x_items=social_items,
        yesterday_clusters=set(),  # Empty since we do hard exclusion above
    )

    # Step 5: Rank clusters
    top_clusters = rank_clusters(clusters, scorer, top_n=config.digest.max_items)
    stats["top_clusters"] = len(top_clusters)

    # Step 6: Distill with LLM
    ranked_with_summaries = await distill_top_clusters(top_clusters, openai_client)
    stats["summaries_generated"] = sum(1 for _, _, _, s in ranked_with_summaries if s)

    if dry_run:
        logger.bind(**stats).info("daily_issue_dry_run_completed")
        return {
            "stats": stats,
            "ranked_with_summaries": ranked_with_summaries,
        }

    # Step 7: Save to database
    await save_issue_to_db(db, issue_date, ranked_with_summaries)

    # Step 8: Write public JSON
    write_public_json(issue_date, ranked_with_summaries)

    logger.bind(**stats).info("daily_issue_build_completed")
    # Return ranked_with_summaries for downstream consumers (e.g., video generation)
    return {
        "stats": stats,
        "ranked_with_summaries": ranked_with_summaries,
    }
