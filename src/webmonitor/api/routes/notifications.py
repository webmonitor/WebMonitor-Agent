"""Notification groups and delivery records."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import Delivery as DeliveryRow, Monitor, utc_now
from webmonitor.schemas.api import Delivery, Group, GroupPatch, GroupSpec, Page
from webmonitor.services import notifications

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/notification-groups", response_model=Page[Group])
async def list_groups(session: DatabaseSession, user: AuthenticatedUser,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await notifications.list_groups(session, limit, offset,
                                           include_members=user.role == "admin")


@router.post("/notification-groups", response_model=Group, status_code=201)
async def create_group(body: GroupSpec, session: DatabaseSession, user: AuthenticatedUser):
    group = await notifications.write_group(session, user, body)
    result = notifications.group_view(group)
    await session.commit()
    return result


@router.patch("/notification-groups/{group_id}", response_model=Group)
async def patch_group(group_id: UUID, body: GroupPatch, session: DatabaseSession,
                      user: AuthenticatedUser):
    group = await notifications.write_group(session, user, body, group_id=group_id)
    result = notifications.group_view(group)
    await session.commit()
    return result


@router.delete("/notification-groups/{group_id}", response_model=Group)
async def delete_group(group_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    group = await notifications.disable_group(session, user, group_id)
    result = notifications.group_view(group)
    await session.commit()
    return result


@router.get("/deliveries", response_model=Page[Delivery])
async def list_deliveries(session: DatabaseSession, user: AuthenticatedUser,
                          limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                          status: Literal["queued", "sending", "retrying", "sent", "failed",
                                          "cancelled"] | None = None,
                          monitor_id: UUID | None = None):
    query = select(DeliveryRow)
    if user.role != "admin":
        query = query.where(DeliveryRow.user_id == user.user_id)
    if status is not None:
        query = query.where(DeliveryRow.status == status)
    if monitor_id is not None:
        query = query.where(DeliveryRow.monitor_id == monitor_id)
    rows = (await session.scalars(query.order_by(DeliveryRow.created_at.desc(), DeliveryRow.id.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    names = {row.id: row.name for row in (await session.scalars(select(Monitor).where(
        Monitor.id.in_({row.monitor_id for row in rows})))).all()}
    return Page[Delivery](items=[_delivery(row, names.get(row.monitor_id, ""))
                                 for row in rows], total=total or 0)


def _delivery(row: DeliveryRow, monitor_name: str = "") -> Delivery:
    return Delivery(id=row.id, monitor_id=row.monitor_id, monitor_name=monitor_name,
        event_id=row.event_id,
        channel=row.channel, recipient=row.recipient, subject=row.subject,
        body_text=row.body_text, status=row.status,
        attempt_count=row.attempt_count, error_code=row.error_code,
        error_message=row.error_message, response_code=row.response_code,
        created_at=row.created_at, sent_at=row.sent_at, failed_at=row.failed_at)


async def _owned_delivery(session: DatabaseSession, user: AuthenticatedUser,
                          delivery_id: UUID) -> DeliveryRow:
    row = await session.get(DeliveryRow, delivery_id, with_for_update=True,
                            populate_existing=True)
    if row is None or (row.user_id != user.user_id and user.role != "admin"):
        raise DomainError("not_found", 404)
    return row


@router.get("/deliveries/{delivery_id}", response_model=Delivery)
async def read_delivery(delivery_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    row = await _owned_delivery(session, user, delivery_id)
    monitor = await session.get(Monitor, row.monitor_id)
    return _delivery(row, monitor.name if monitor is not None else "")


@router.post("/deliveries/{delivery_id}/retry", response_model=Delivery)
async def retry_delivery(delivery_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    """Requeue one delivery the user can see, resetting its attempt history."""
    row = await _owned_delivery(session, user, delivery_id)
    if row.status not in ("failed", "cancelled"):
        raise DomainError("delivery_not_retryable", 409, details={"status": row.status})
    row.status, row.available_at = "queued", utc_now()
    row.attempt_count = 0
    row.lease_owner = row.lease_expires_at = None
    row.error_code = row.error_message = row.response_code = None
    row.failed_at = row.cancelled_at = None
    await session.flush()
    monitor = await session.get(Monitor, row.monitor_id)
    result = _delivery(row, monitor.name if monitor is not None else "")
    await session.commit()
    return result
