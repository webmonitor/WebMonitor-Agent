"""Change events across the monitors a user may read."""
from uuid import UUID

from fastapi import APIRouter, Query

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.schemas.api import EventView, Page
from webmonitor.schemas.notifications import EventType
from webmonitor.services import events

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=Page[EventView])
async def list_events(session: DatabaseSession, user: AuthenticatedUser,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      monitor_id: UUID | None = None, event_type: EventType | None = None,
                      acknowledged: bool | None = None):
    return await events.list_events(
        session,
        user,
        limit=limit,
        offset=offset,
        monitor_id=monitor_id,
        event_type=event_type,
        acknowledged=acknowledged,
    )


@router.post("/{event_id}/acknowledge", response_model=EventView)
async def acknowledge(event_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    result = await events.acknowledge_event(session, user, event_id)
    await session.commit()
    return result
