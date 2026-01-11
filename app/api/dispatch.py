"""Dispatch API endpoints for sending digests to various destinations."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.dependencies import CurrentUser, DBSession
from app.models.issue import Issue
from app.services.dispatch import (
    dispatch_issue,
    get_latest_issue_date,
    get_registry,
)

router = APIRouter()


class DispatchResultResponse(BaseModel):
    """Response model for a single dispatch result."""

    destination: str
    success: bool
    message: str


class DispatchResponse(BaseModel):
    """Response model for dispatch operation."""

    issue_date: str
    results: list[DispatchResultResponse]


@router.get("/dispatch/destinations")
async def list_destinations() -> dict[str, list[str]]:
    """List all available dispatch destinations."""
    registry = get_registry()
    return {"destinations": registry.list_available()}


@router.post("/dispatch/latest", response_model=DispatchResponse)
async def dispatch_latest(
    db: DBSession,
    user: CurrentUser,
    destinations: str | None = Query(
        default=None,
        description="Comma-separated list of destinations (e.g., 'discord,email'). Defaults to all.",
    ),
) -> DispatchResponse:
    """
    Dispatch the latest issue to specified destinations.

    Requires authentication. Use `destinations` query param to specify
    which destinations to send to. Defaults to all available destinations.

    Examples:
    - POST /api/dispatch/latest?destinations=discord
    - POST /api/dispatch/latest?destinations=discord,email
    - POST /api/dispatch/latest (sends to all)
    """
    latest_date = await get_latest_issue_date(db)

    if not latest_date:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No issues found",
        )

    dest_list = None
    if destinations:
        dest_list = [d.strip() for d in destinations.split(",") if d.strip()]

    results = await dispatch_issue(db, latest_date, dest_list)

    return DispatchResponse(
        issue_date=str(latest_date),
        results=[
            DispatchResultResponse(
                destination=r.destination,
                success=r.success,
                message=r.message,
            )
            for r in results
        ],
    )


@router.post("/dispatch/{issue_date}", response_model=DispatchResponse)
async def dispatch_by_date(
    issue_date: date,
    db: DBSession,
    user: CurrentUser,
    destinations: str | None = Query(
        default=None,
        description="Comma-separated list of destinations (e.g., 'discord,email'). Defaults to all.",
    ),
) -> DispatchResponse:
    """
    Dispatch a specific issue to specified destinations.

    Requires authentication. Use `destinations` query param to specify
    which destinations to send to. Defaults to all available destinations.

    Examples:
    - POST /api/dispatch/2026-01-11?destinations=discord
    - POST /api/dispatch/2026-01-11?destinations=discord,email
    - POST /api/dispatch/2026-01-11 (sends to all)
    """
    # Verify issue exists
    result = await db.execute(select(Issue).where(Issue.issue_date == issue_date))
    issue = result.scalar_one_or_none()

    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No issue found for {issue_date}",
        )

    dest_list = None
    if destinations:
        dest_list = [d.strip() for d in destinations.split(",") if d.strip()]

    results = await dispatch_issue(db, issue_date, dest_list)

    return DispatchResponse(
        issue_date=str(issue_date),
        results=[
            DispatchResultResponse(
                destination=r.destination,
                success=r.success,
                message=r.message,
            )
            for r in results
        ],
    )
