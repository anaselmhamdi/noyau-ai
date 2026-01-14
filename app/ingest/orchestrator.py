from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppConfig, get_config
from app.core.datetime_utils import to_naive_utc, utc_now
from app.core.logging import get_logger
from app.ingest.base import BaseFetcher, RawContent
from app.ingest.bluesky import create_bluesky_fetcher
from app.ingest.devto import create_devto_fetcher
from app.ingest.reddit import create_reddit_fetcher
from app.ingest.rss import create_rss_fetchers
from app.ingest.youtube import create_youtube_fetcher
from app.models.content import ContentItem, ContentSource, MetricsSnapshot

logger = get_logger(__name__)


def create_all_fetchers(config: AppConfig) -> list[BaseFetcher]:
    """Create all configured fetchers."""
    fetchers: list[BaseFetcher] = []

    # RSS and GitHub releases
    fetchers.extend(create_rss_fetchers(config))

    # Reddit
    reddit = create_reddit_fetcher(config)
    if reddit:
        fetchers.append(reddit)

    # dev.to
    devto = create_devto_fetcher(config)
    if devto:
        fetchers.append(devto)

    # YouTube
    youtube = create_youtube_fetcher(config)
    if youtube:
        fetchers.append(youtube)

    # Bluesky
    bluesky = create_bluesky_fetcher(config)
    if bluesky:
        fetchers.append(bluesky)

    return fetchers


async def upsert_content_item(
    db: AsyncSession,
    raw: RawContent,
) -> ContentItem:
    """
    Upsert a content item by URL.

    If item exists, returns existing item.
    If item is new, creates and returns it.
    """
    # Check if item exists
    result = await db.execute(select(ContentItem).where(ContentItem.url == raw.url))
    existing = result.scalar_one_or_none()

    if existing:
        item: ContentItem = existing
        return item

    # Map source string to enum
    source_map = {
        "x": ContentSource.X,
        "reddit": ContentSource.REDDIT,
        "github": ContentSource.GITHUB,
        "youtube": ContentSource.YOUTUBE,
        "devto": ContentSource.DEVTO,
        "rss": ContentSource.RSS,
        "status": ContentSource.STATUS,
        "bluesky": ContentSource.BLUESKY,
    }
    source = source_map.get(raw.source, ContentSource.RSS)

    # Create new item
    item = ContentItem(
        source=source,
        source_id=raw.source_id,
        url=raw.url,
        title=raw.title,
        author=raw.author,
        published_at=to_naive_utc(raw.published_at),
        text=raw.text,
    )
    db.add(item)
    await db.flush()

    logger.bind(url=raw.url, source=raw.source).debug("content_item_created")

    return item


async def create_metrics_snapshot(
    db: AsyncSession,
    item_id: str,
    metrics: dict,
) -> MetricsSnapshot:
    """Create a metrics snapshot for an item."""
    snapshot = MetricsSnapshot(
        item_id=item_id,
        captured_at=utc_now(),
        metrics_json=metrics,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def run_hourly_ingest(db: AsyncSession) -> dict:
    """
    Run the hourly ingest job.

    Fetches from all sources, upserts content items,
    and creates metrics snapshots.

    Returns:
        Dict with stats about the ingest run
    """
    config = get_config()
    fetchers = create_all_fetchers(config)

    stats = {
        "total_items": 0,
        "new_items": 0,
        "existing_items": 0,
        "snapshots_created": 0,
        "errors": 0,
    }

    logger.bind(fetcher_count=len(fetchers)).info("hourly_ingest_started")

    for fetcher in fetchers:
        fetcher_stats = {
            "items": 0,
            "errors": 0,
        }

        try:
            async for raw_item in fetcher.fetch():
                try:
                    # Upsert content item
                    item = await upsert_content_item(db, raw_item)

                    # Track if new or existing
                    if item.fetched_at and (utc_now() - item.fetched_at).seconds < 60:
                        stats["new_items"] += 1
                    else:
                        stats["existing_items"] += 1

                    # Create metrics snapshot
                    await create_metrics_snapshot(db, str(item.id), raw_item.metrics)
                    stats["snapshots_created"] += 1

                    fetcher_stats["items"] += 1
                    stats["total_items"] += 1

                except Exception as e:
                    logger.warning(
                        f"ingest_item_error: {fetcher.source_name} | {raw_item.url} | {e}"
                    )
                    fetcher_stats["errors"] += 1
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"fetcher_error: {fetcher.source_name} | {e}")
            stats["errors"] += 1

        logger.info(
            f"fetcher_completed: {fetcher.source_name} | items={fetcher_stats['items']} errors={fetcher_stats['errors']}"
        )

    # Commit all changes
    await db.commit()

    logger.info(f"hourly_ingest_completed: {stats}")
    return stats
