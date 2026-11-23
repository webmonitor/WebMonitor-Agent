"""Notification groups and delivery records."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import Delivery as DeliveryRow
from webmonitor.models import Monitor
from webmonitor.schemas.api import Delivery, Group, GroupPatch, GroupSpec, Page
from webmonitor.services import notifications

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/notification-groups", response_model=Page[Group])
async def list_groups(
    session: DatabaseSession,
    user: AuthenticatedUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await notifications.list_groups(
        session, limit, offset, include_members=user.role == "admin"
    )


@router.post("/notification-groups", response_model=Group, status_code=201)
async def create_group(body: GroupSpec, session: DatabaseSession, user: AuthenticatedUser):
    group = await notifications.write_group(session, user, body)
    result = notifications.group_view(group)
    await session.commit()
    return result


@router.patch("/notification-groups/{group_id}", response_model=Group)
async def patch_group(
    group_id: UUID, body: GroupPatch, session: DatabaseSession, user: AuthenticatedUser
):
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
async def list_deliveries(
    session: DatabaseSession,
    user: AuthenticatedUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Literal["queued", "sending", "retrying", "sent", "failed", "cancelled"] | None = None,
    monitor_id: UUID | None = None,
):
    return await notifications.list_deliveries(
        session, user, limit=limit, offset=offset, status=status, monitor_id=monitor_id
    )


async def _owned_delivery(
    session: DatabaseSession, user: AuthenticatedUser, delivery_id: UUID
) -> DeliveryRow:
    row = await session.get(DeliveryRow, delivery_id, with_for_update=True, populate_existing=True)
    if row is None or (row.user_id != user.user_id and user.role != "admin"):
        raise DomainError("not_found", 404)
    return row


@router.get("/deliveries/{delivery_id}", response_model=Delivery)
async def read_delivery(delivery_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    row = await _owned_delivery(session, user, delivery_id)
    monitor = await session.get(Monitor, row.monitor_id)
    return notifications.delivery_view(
        row, monitor.name if monitor is not None else "", include_recipient=user.role == "admin"
    )


@router.post("/deliveries/{delivery_id}/retry", response_model=Delivery)
async def retry_delivery(delivery_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    """Requeue one delivery the user can see, resetting its attempt history."""
    result = await notifications.retry_delivery(session, user, delivery_id)
    await session.commit()
    return result
