"""Notification groups and delivery records."""
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import EmailDelivery
from webmonitor.schemas.api import Delivery, Group, GroupPatch, GroupSpec, Page
from webmonitor.services import notifications

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/notification-groups", response_model=Page[Group])
async def list_groups(session: DatabaseSession, user: AuthenticatedUser,
                      limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await notifications.list_groups(session, limit, offset)


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


@router.get("/email-deliveries", response_model=Page[Delivery])
async def list_deliveries(session: DatabaseSession, user: AuthenticatedUser,
                          limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    query = select(EmailDelivery)
    if user.role != "admin":
        query = query.where(EmailDelivery.user_id == user.user_id)
    rows = (await session.scalars(query.order_by(EmailDelivery.created_at.desc(), EmailDelivery.id.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[Delivery](items=[_delivery(row) for row in rows], total=total or 0)


def _delivery(row: EmailDelivery) -> Delivery:
    return Delivery(id=row.id, monitor_id=row.monitor_id, event_id=row.event_id,
        recipient=row.recipient, subject=row.subject, body_text=row.body_text,
        status=row.status,
        attempt_count=row.attempt_count, error_code=row.error_code,
        error_message=row.error_message, smtp_response_code=row.smtp_response_code,
        created_at=row.created_at, sent_at=row.sent_at, failed_at=row.failed_at)


@router.get("/email-deliveries/{delivery_id}", response_model=Delivery)
async def read_delivery(delivery_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    row = await session.get(EmailDelivery, delivery_id)
    if row is None or (row.user_id != user.user_id and user.role != "admin"):
        raise DomainError("not_found", 404)
    return _delivery(row)
