from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    """Request body for creating an event."""

    event_name: str = Field(max_length=100)
    properties: dict[str, Any] = Field(default_factory=dict)


class EventResponse(BaseModel):
    """Response after creating an event."""

    ok: bool = True
    event_id: str
    ts: datetime
