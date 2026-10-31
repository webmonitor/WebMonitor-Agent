"""Change events across the monitors a user may read."""
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import Event, Monitor, utc_now
from webmonitor.schemas.api import EventView, Page

router = APIRouter(prefix="/api/v1/events", tags=["events"])


def _view(event: Event, monitor_name: str) -> EventView:
    return EventView(id=event.id, monitor_id=event.monitor_id, monitor_name=monitor_name,
        job_id=event.job_id, snapshot_id=event.snapshot_id, type=event.type,
        change=event.change or {}, created_at=event.created_at,
        acknowledged_at=event.acknowledged_at)


@router.get("", response_model=Page[EventView])
async def list_events(session: DatabaseSession, user: AuthenticatedUser,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                      monitor_id: UUID | None = None):
    query = select(Event)
    if monitor_id is not None:
        query = query.where(Event.monitor_id == monitor_id)
    if user.role != "admin":
        query = query.join(Monitor, Monitor.id == Event.monitor_id).where(
            Monitor.user_id == user.user_id)
    rows = (await session.scalars(query.order_by(Event.created_at.desc(), Event.id.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    names = {row.id: row.name for row in (await session.scalars(select(Monitor).where(
        Monitor.id.in_({row.monitor_id for row in rows})))).all()}
    return Page[EventView](items=[_view(row, names.get(row.monitor_id, "")) for row in rows],
                           total=total or 0)


@router.post("/{event_id}/acknowledge", response_model=EventView)
async def acknowledge(event_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    event = await session.scalar(select(Event).where(Event.id == event_id).with_for_update()
        .execution_options(populate_existing=True))
    if event is None:
        raise DomainError("not_found", 404)
    monitor = await session.get(Monitor, event.monitor_id)
    if monitor is not None and monitor.user_id != user.user_id and user.role != "admin":
        raise DomainError("forbidden", 403)
    if event.acknowledged_at is None:
        event.acknowledged_at = utc_now()
        event.acknowledged_by_user_id = user.user_id
    result = _view(event, monitor.name if monitor is not None else "")
    await session.commit()
    return result
