from fastapi import APIRouter

from app.dependencies import CurrentUserOptional, DBSession
from app.models.event import Event
from app.schemas.event import EventCreate, EventResponse

router = APIRouter()


@router.post("/events", response_model=EventResponse)
async def create_event(
    body: EventCreate,
    db: DBSession,
    user: CurrentUserOptional,
) -> EventResponse:
    """
    Record an analytics event.

    Events are associated with users if authenticated, otherwise anonymous.
    """
    event = Event(
        user_id=user.id if user else None,
        event_name=body.event_name,
        properties_json=body.properties,
    )
    db.add(event)
    await db.flush()

    return EventResponse(
        ok=True,
        event_id=str(event.id),
        ts=event.ts,
    )
