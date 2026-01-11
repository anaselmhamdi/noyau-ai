from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Citation


class IssueItemPublic(BaseModel):
    """Public view of an issue item (soft-gated)."""

    rank: int = Field(ge=1, le=10)
    headline: str
    teaser: str
    locked: bool = False


class IssueItemFull(BaseModel):
    """Full view of an issue item (authenticated)."""

    rank: int = Field(ge=1, le=10)
    headline: str
    teaser: str
    takeaway: str
    why_care: str | None = None
    bullets: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    locked: bool = False


class MissedItem(BaseModel):
    """Item from yesterday's issue for 'You may have missed' section."""

    headline: str
    teaser: str


class IssueResponse(BaseModel):
    """Response for /api/issues/{date} endpoint."""

    date: date
    items: list[IssueItemPublic | IssueItemFull]
    missed_items: list[MissedItem] = Field(default_factory=list)
