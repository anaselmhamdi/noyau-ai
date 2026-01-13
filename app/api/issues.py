from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_config
from app.dependencies import CurrentUser, CurrentUserOptional, DBSession
from app.models.cluster import Cluster, ClusterSummary
from app.models.issue import Issue
from app.pipeline.issue_builder import build_daily_issue, get_missed_from_yesterday
from app.schemas.common import Citation
from app.schemas.issue import IssueItemFull, IssueItemPublic, IssueResponse, MissedItem

router = APIRouter()


@router.get("/issues/dates")
async def get_issue_dates(db: DBSession) -> dict[str, list[str]]:
    """
    Get all published issue dates for sitemap generation.

    Returns dates in descending order (newest first).
    """
    result = await db.execute(select(Issue.issue_date).order_by(Issue.issue_date.desc()))
    dates = [str(d) for d in result.scalars().all()]
    return {"dates": dates}


@router.get("/issues/preview", response_model=IssueResponse)
async def preview_issue(
    db: DBSession,
    user: CurrentUser,
    issue_date: date | None = Query(default=None, alias="date"),
) -> IssueResponse:
    """
    Preview today's issue without publishing.

    Runs the full pipeline (fetch, cluster, score, distill) but
    does not save to database or write public JSON.

    Requires authentication.
    """
    if issue_date is None:
        issue_date = date.today()

    result = await build_daily_issue(db, issue_date, dry_run=True)
    ranked_with_summaries = result.get("ranked_with_summaries", [])

    items: list[IssueItemFull] = []
    for rank, (identity, content_items, score_info, summary) in enumerate(
        ranked_with_summaries, start=1
    ):
        if summary:
            items.append(
                IssueItemFull(
                    rank=rank,
                    headline=summary.headline,
                    teaser=summary.teaser,
                    takeaway=summary.takeaway,
                    why_care=summary.why_care,
                    bullets=summary.bullets,
                    citations=[Citation(**c.model_dump()) for c in summary.citations],
                    confidence=summary.confidence,
                    locked=False,
                )
            )

    # Include missed items in preview for consistency
    missed_clusters = await get_missed_from_yesterday(db, limit=3)
    missed_items = [
        MissedItem(headline=c.summary.headline, teaser=c.summary.teaser)
        for c in missed_clusters
        if c.summary
    ]

    return IssueResponse(date=issue_date, items=items, missed_items=missed_items)


@router.get("/issues/latest", response_model=IssueResponse)
async def get_latest_issue(
    db: DBSession,
    user: CurrentUserOptional,
    view: str = Query(default="public", pattern="^(public|full)$"),
) -> IssueResponse:
    """
    Get the most recent published issue.

    - view=public: Returns items 1-5 fully, items 6-10 as headline+teaser only (locked)
    - view=full: Requires authentication, returns all items fully
    """
    # Find latest issue date
    result = await db.execute(select(Issue.issue_date).order_by(Issue.issue_date.desc()).limit(1))
    latest_date = result.scalar_one_or_none()

    if not latest_date:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No issues published yet",
        )

    # Reuse existing endpoint logic
    response: IssueResponse = await get_issue(latest_date, db, user, view)
    return response


@router.get("/issues/{issue_date}", response_model=IssueResponse)
async def get_issue(
    issue_date: date,
    db: DBSession,
    user: CurrentUserOptional,
    view: str = Query(default="public", pattern="^(public|full)$"),
) -> IssueResponse:
    """
    Get a daily issue by date.

    - view=public: Returns items 1-5 fully, items 6-10 as headline+teaser only (locked)
    - view=full: Requires authentication, returns all items fully
    """
    config = get_config()

    # Check if issue exists
    issue_result = await db.execute(select(Issue).where(Issue.issue_date == issue_date))
    issue = issue_result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No issue found for {issue_date}",
        )

    # Get clusters with summaries for this date, ordered by score
    clusters_result = await db.execute(
        select(Cluster)
        .options(selectinload(Cluster.summary))
        .where(Cluster.issue_date == issue_date)
        .order_by(Cluster.cluster_score.desc())
        .limit(config.digest.max_items)
    )
    clusters = clusters_result.scalars().all()

    # Determine if user can see full content
    is_authenticated = user is not None
    show_full = is_authenticated and view == "full"

    items: list[IssueItemPublic | IssueItemFull] = []
    display_rank = 0
    for cluster in clusters:
        summary: ClusterSummary | None = cluster.summary

        if not summary:
            continue

        display_rank += 1
        if display_rank > config.digest.max_items:
            break

        if show_full or display_rank <= config.digest.free_items:
            # Return full item
            items.append(
                IssueItemFull(
                    rank=display_rank,
                    headline=summary.headline,
                    teaser=summary.teaser,
                    takeaway=summary.takeaway,
                    why_care=summary.why_care,
                    bullets=summary.bullets_json,
                    citations=[Citation(**c) for c in summary.citations_json],
                    confidence=summary.confidence.value,
                    locked=False,
                )
            )
        else:
            # Return locked item (headline + teaser only)
            items.append(
                IssueItemPublic(
                    rank=display_rank,
                    headline=summary.headline,
                    teaser=summary.teaser,
                    locked=True,
                )
            )

    # Fetch "You may have missed" items from yesterday
    missed_clusters = await get_missed_from_yesterday(db, limit=3)
    missed_items = [
        MissedItem(headline=c.summary.headline, teaser=c.summary.teaser)
        for c in missed_clusters
        if c.summary
    ]

    return IssueResponse(date=issue_date, items=items, missed_items=missed_items)
