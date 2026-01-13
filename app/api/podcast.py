"""Podcast API routes for RSS feed and episode listing."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select

from app.config import get_config
from app.dependencies import DBSession
from app.models.issue import Issue
from app.podcast.rss_feed import generate_podcast_rss, get_default_feed_config
from app.schemas.podcast import PodcastEpisode, PodcastFeedInfo

router = APIRouter()


@router.get("/podcast/feed.xml", response_class=Response)
async def get_podcast_feed(db: DBSession) -> Response:
    """
    Get the podcast RSS feed.

    Returns an iTunes-compatible RSS 2.0 feed for podcast directories.
    """
    # Get episodes from database
    stmt = (
        select(Issue)
        .where(Issue.podcast_audio_url.isnot(None))
        .order_by(Issue.issue_date.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    issues = list(result.scalars().all())

    if not issues:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No podcast episodes available",
        )

    # Count total episodes for episode numbering
    total_count = len(issues)

    episodes = []
    for i, issue in enumerate(issues):
        episode_number = total_count - i
        episodes.append(
            {
                "issue_date": issue.issue_date,
                "episode_number": episode_number,
                "audio_url": issue.podcast_audio_url,
                "duration_seconds": issue.podcast_duration_seconds or 480,
                "published_at": issue.created_at,
            }
        )

    # Get feed config
    config = get_default_feed_config()

    # Update from app config if available
    app_config = get_config()
    if hasattr(app_config, "podcast") and app_config.podcast:
        podcast_cfg = app_config.podcast
        if hasattr(podcast_cfg, "feed") and podcast_cfg.feed:
            feed_cfg = podcast_cfg.feed
            config.update(
                {
                    "title": getattr(feed_cfg, "title", config["title"]),
                    "description": getattr(feed_cfg, "description", config["description"]),
                    "author": getattr(feed_cfg, "author", config["author"]),
                    "category": getattr(feed_cfg, "category", config["category"]),
                }
            )

    # Generate RSS XML
    xml_content = generate_podcast_rss(episodes, config)

    return Response(
        content=xml_content,
        media_type="application/rss+xml",
        headers={
            "Cache-Control": "public, max-age=900",  # 15 minutes
        },
    )


@router.get("/podcast/episodes", response_model=list[PodcastEpisode])
async def list_episodes(
    db: DBSession,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[PodcastEpisode]:
    """
    List podcast episodes with pagination.

    Returns episodes in reverse chronological order (newest first).
    """
    # Count total episodes
    count_stmt = select(func.count()).where(Issue.podcast_audio_url.isnot(None))
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    # Get paginated episodes
    stmt = (
        select(Issue)
        .where(Issue.podcast_audio_url.isnot(None))
        .order_by(Issue.issue_date.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    issues = list(result.scalars().all())

    episodes = []
    for i, issue in enumerate(issues):
        # Calculate episode number (counting from first episode)
        episode_number = total_count - offset - i

        formatted_date = issue.issue_date.strftime("%B %d, %Y")
        episodes.append(
            PodcastEpisode(
                issue_date=issue.issue_date,
                episode_number=episode_number,
                title=f"Episode {episode_number}: {formatted_date}",
                description=f"Your daily tech briefing for {formatted_date}.",
                audio_url=issue.podcast_audio_url,
                youtube_url=issue.podcast_youtube_url,
                duration_seconds=issue.podcast_duration_seconds or 480,
                published_at=issue.created_at,
            )
        )

    return episodes


@router.get("/podcast/latest", response_model=PodcastEpisode)
async def get_latest_episode(db: DBSession) -> PodcastEpisode:
    """
    Get the most recent podcast episode.
    """
    # Count total episodes for episode number
    count_stmt = select(func.count()).where(Issue.podcast_audio_url.isnot(None))
    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    # Get latest episode
    stmt = (
        select(Issue)
        .where(Issue.podcast_audio_url.isnot(None))
        .order_by(Issue.issue_date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No podcast episodes available",
        )

    formatted_date = issue.issue_date.strftime("%B %d, %Y")

    return PodcastEpisode(
        issue_date=issue.issue_date,
        episode_number=total_count,
        title=f"Episode {total_count}: {formatted_date}",
        description=f"Your daily tech briefing for {formatted_date}.",
        audio_url=issue.podcast_audio_url,
        youtube_url=issue.podcast_youtube_url,
        duration_seconds=issue.podcast_duration_seconds or 480,
        published_at=issue.created_at,
    )


@router.get("/podcast/info", response_model=PodcastFeedInfo)
async def get_podcast_info(db: DBSession) -> PodcastFeedInfo:
    """
    Get podcast feed metadata and subscription info.
    """
    # Count episodes
    count_stmt = select(func.count()).where(Issue.podcast_audio_url.isnot(None))
    count_result = await db.execute(count_stmt)
    episode_count = count_result.scalar() or 0

    # Get latest episode if available
    latest_episode = None
    if episode_count > 0:
        latest_episode = await get_latest_episode(db)

    # Get feed config
    config = get_default_feed_config()

    return PodcastFeedInfo(
        title=config["title"],
        description=config["description"],
        author=config["author"],
        feed_url=config["feed_url"],
        website_url=config["website_url"],
        artwork_url=config["artwork_url"],
        category=config["category"],
        episode_count=episode_count,
        latest_episode=latest_episode,
    )


@router.get("/podcast/episode/{issue_date}", response_model=PodcastEpisode)
async def get_episode_by_date(
    issue_date: date,
    db: DBSession,
) -> PodcastEpisode:
    """
    Get a specific podcast episode by date.
    """
    # Get the issue
    stmt = select(Issue).where(
        Issue.issue_date == issue_date,
        Issue.podcast_audio_url.isnot(None),
    )
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No podcast episode found for {issue_date}",
        )

    # Count episodes up to this date for episode number
    count_stmt = select(func.count()).where(
        Issue.podcast_audio_url.isnot(None),
        Issue.issue_date <= issue_date,
    )
    count_result = await db.execute(count_stmt)
    episode_number = count_result.scalar() or 1

    formatted_date = issue.issue_date.strftime("%B %d, %Y")

    return PodcastEpisode(
        issue_date=issue.issue_date,
        episode_number=episode_number,
        title=f"Episode {episode_number}: {formatted_date}",
        description=f"Your daily tech briefing for {formatted_date}.",
        audio_url=issue.podcast_audio_url,
        youtube_url=issue.podcast_youtube_url,
        duration_seconds=issue.podcast_duration_seconds or 480,
        published_at=issue.created_at,
    )
