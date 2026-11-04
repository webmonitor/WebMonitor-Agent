"""Notification groups, recipient resolution and leased email delivery."""
from datetime import timedelta
from email.utils import parseaddr
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import (
    EmailDelivery,
    Event,
    Monitor,
    NotificationGroup,
    utc_now,
)
from webmonitor.notifications.rendering import render_email
from webmonitor.schemas.api import Group, MemberSpec, Page
from webmonitor.schemas.templates import EmailTemplateConfig
from webmonitor.security.auth import CurrentUser, require_admin
from webmonitor.services.jobs import LEASE_SECONDS


def group_view(group: NotificationGroup, *, include_members: bool = True) -> Group:
    """Members are an administrator secret; everyone else sees how many are active."""
    active = [item for item in group.members or [] if item.get("active", True)]
    return Group(id=group.id, name=group.name, enabled=group.enabled,
        members=[MemberSpec(email=item["email"], active=item.get("active", True))
                 for item in group.members or []] if include_members else [],
        member_count=len(active),
        created_at=group.created_at, updated_at=group.updated_at)


async def list_groups(session: AsyncSession, limit: int, offset: int, *,
                      include_members: bool = True) -> Page[Group]:
    query = select(NotificationGroup).where(NotificationGroup.deleted_at.is_(None))
    rows = (await session.scalars(query.order_by(NotificationGroup.name)
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[Group](items=[group_view(row, include_members=include_members) for row in rows],
                       total=total or 0)


async def get_group(session: AsyncSession, group_id: UUID, *, lock: bool = False) -> NotificationGroup:
    query = select(NotificationGroup).where(NotificationGroup.id == group_id,
                                            NotificationGroup.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    group = await session.scalar(query.execution_options(populate_existing=True))
    if group is None:
        raise DomainError("not_found", 404)
    return group


def _members(members: list[MemberSpec]) -> list[dict[str, Any]]:
    return [{"email": str(member.email), "active": member.active} for member in members]


async def _referencing_monitors(session: AsyncSession, group_id: UUID) -> list[UUID]:
    """Archived monitors keep their settings but never block a group deletion."""
    rows = await session.scalars(select(Monitor.id).where(
        Monitor.archived_at.is_(None),
        Monitor.notification_group_ids.contains([str(group_id)])))
    return list(rows.all())


async def _require_unreferenced(session: AsyncSession, group_id: UUID) -> None:
    monitors = await _referencing_monitors(session, group_id)
    if monitors:
        raise DomainError("group_in_use", 409,
                          details={"monitor_ids": [str(item) for item in monitors]})


async def write_group(session: AsyncSession, user: CurrentUser, body, *,
                      group_id: UUID | None = None) -> NotificationGroup:
    require_admin(user)
    try:
        async with session.begin_nested():
            if group_id is None:
                group = NotificationGroup(name=body.name.strip(), enabled=getattr(body, "enabled", True),
                    members=_members(getattr(body, "members", [])), created_by_user_id=user.user_id)
                session.add(group)
                await session.flush()
            else:
                group = await get_group(session, group_id, lock=True)
                if body.name is not None:
                    group.name = body.name
                if getattr(body, "enabled", None) is not None:
                    if not body.enabled:
                        await _require_unreferenced(session, group.id)
                    group.enabled = body.enabled
                if getattr(body, "members", None) is not None:
                    group.members = _members(body.members)
                await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError("group_name_conflict", 409) from None
        raise
    return group


async def disable_group(session: AsyncSession, user: CurrentUser, group_id: UUID) -> NotificationGroup:
    require_admin(user)
    group = await get_group(session, group_id, lock=True)
    await _require_unreferenced(session, group.id)
    group.enabled = False
    group.deleted_at = utc_now()
    group.members = []
    await session.flush()
    return group


async def load_recipients(session: AsyncSession, group_ids: list[UUID] | list[str], *,
                          lock: bool = False) -> list[dict]:
    """Freeze every authorized source, deduplicating email delivery addresses."""
    ids = {UUID(str(item)) for item in group_ids}
    query = select(NotificationGroup).where(
        NotificationGroup.id.in_(ids), NotificationGroup.enabled.is_(True),
        NotificationGroup.deleted_at.is_(None)).order_by(NotificationGroup.id)
    if lock:
        query = query.with_for_update(read=True)
    groups = (await session.scalars(query)).all()
    if len(groups) != len(ids):
        raise DomainError("notification_routes_invalid", 409)
    sources: dict[str, list[str]] = {}
    for group in groups:
        for member in group.members or []:
            if member.get("active", True):
                sources.setdefault(member["email"], []).append(str(group.id))
    if not sources:
        raise DomainError("notification_recipients_empty", 409)
    return [{"email": email, "group_ids": sorted(set(sources[email]))}
            for email in sorted(sources)]


async def approved_recipients(session: AsyncSession, monitor: Monitor) -> list[dict]:
    """Current memberships may revoke an approval, but never expand one."""
    groups = (await session.scalars(select(NotificationGroup).where(
        NotificationGroup.id.in_([UUID(item) for item in monitor.notification_group_ids]),
        NotificationGroup.enabled.is_(True), NotificationGroup.deleted_at.is_(None)))).all()
    active = {str(group.id): {member["email"] for member in group.members or []
                             if member.get("active", True)} for group in groups}
    recipients = []
    for recipient in monitor.approved_recipients:
        sources = [source for source in recipient["group_ids"]
                   if recipient["email"] in active.get(source, set())]
        if sources:
            recipients.append({"email": recipient["email"], "group_ids": sources})
    return recipients


def recipients_emails(recipients: list[dict]) -> list[str]:
    return sorted({item["email"] for item in recipients})


def _timezone(monitor: Monitor) -> str:
    """Dates are normalized to the monitor's zone; the mail shows them there."""
    return monitor.timezone or "UTC"


def _payload(monitor: Monitor, event: Event, fields: dict) -> dict:
    return {
        "monitor": {"id": str(monitor.id), "name": monitor.name, "url": monitor.url,
                    "timezone": _timezone(monitor)},
        "event": {"id": str(event.id), "type": event.type,
                  "detected_at": event.created_at.isoformat()},
        "change": {"before": event.change.get("before"),
                   "after": event.change.get("after", {}),
                   "summary": event.change.get("summary", ""),
                   "differences": event.change.get("differences") or [],
                   "labels": event.change.get("labels") or {}},
        "fields": fields,
        "evidence_url": f"{get_settings().app_origin}/app/monitors/{monitor.id}",
    }


async def enqueue_event_deliveries(session: AsyncSession, monitor: Monitor, event: Event,
                                   fields: dict) -> None:
    """Flush only. Disabled or empty routes never undo a valid snapshot."""
    recipients = await approved_recipients(session, monitor)
    if not recipients:
        raise DomainError("notification_recipients_empty", 409)
    payload = _payload(monitor, event, fields)
    event.payload = payload
    try:
        template = (EmailTemplateConfig.model_validate(monitor.email_template)
                    if monitor.email_template else None)
    except ValueError:
        # A frozen snapshot that no longer parses stays inert; the snapshot itself
        # is still the valid record of what the monitor was approved with.
        raise DomainError("template_unavailable", 409) from None
    rendered = render_email(event.type, payload, template)
    domain = parseaddr(get_settings().mail_from)[1].split("@")[-1] or "webmonitor.local"
    for recipient in recipients:
        delivery_id = uuid4()
        session.add(EmailDelivery(id=delivery_id, user_id=monitor.user_id,
            monitor_id=monitor.id, event_id=event.id, recipient=recipient["email"],
            subject=rendered["subject"], html=rendered["html"], body_text=rendered["text"],
            payload={**payload, "recipient_sources": recipient["group_ids"]},
            status="queued", attempt_count=0,
            available_at=event.created_at, message_id=f"<{delivery_id}@{domain}>"))
    await session.flush()


async def claim_delivery(session: AsyncSession, worker_id: str) -> EmailDelivery | None:
    now = utc_now()
    delivery = await session.scalar(select(EmailDelivery).where(
        EmailDelivery.available_at <= now,
        or_(EmailDelivery.status.in_(("queued", "retrying")),
            and_(EmailDelivery.status == "sending",
                 EmailDelivery.lease_expires_at <= now)),
    ).order_by(EmailDelivery.available_at, EmailDelivery.created_at)
        .with_for_update(skip_locked=True).limit(1).execution_options(populate_existing=True))
    if delivery is None:
        return None
    if delivery.attempt_count >= get_settings().max_attempts:
        # Attempts ran out before anyone could try again; stop rescheduling it.
        delivery.status, delivery.failed_at = "failed", now
        delivery.error_code = "delivery_attempts_exhausted"
        delivery.error_message = "Delivery attempts exhausted"
        delivery.lease_owner = delivery.lease_expires_at = None
        await session.flush()
        return None
    delivery.status = "sending"
    delivery.attempt_count += 1
    delivery.lease_owner = worker_id
    delivery.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    await session.flush()
    return delivery


async def authorized(session: AsyncSession, delivery: EmailDelivery) -> bool:
    """Only this monitor's approved, still-active sources authorize a queued mail."""
    monitor = await session.get(Monitor, delivery.monitor_id)
    sources = set((delivery.payload or {}).get("recipient_sources") or [])
    if monitor is None or not sources:
        return False
    recipients = await approved_recipients(session, monitor)
    return any(recipient["email"] == delivery.recipient
               and sources.intersection(recipient["group_ids"]) for recipient in recipients)


async def finish_delivery(session: AsyncSession, delivery: EmailDelivery, *, worker_id: str,
                          failure=None, response_code: int | None = None) -> None:
    if delivery.lease_owner != worker_id or delivery.status != "sending":
        return
    now = utc_now()
    delivery.lease_owner = delivery.lease_expires_at = None
    delivery.smtp_response_code = getattr(failure, "response_code", None) if failure else response_code
    delivery.error_code = failure.code if failure else None
    delivery.error_message = failure.message if failure else None
    if failure is None:
        delivery.status, delivery.sent_at = "sent", now
    elif getattr(failure, "retryable", False) and delivery.attempt_count < get_settings().max_attempts:
        delivery.status = "retrying"
        delivery.available_at = now + timedelta(seconds=60 if delivery.attempt_count == 1 else 300)
    else:
        delivery.status, delivery.failed_at = "failed", now
    await session.flush()


async def cancel_delivery(session: AsyncSession, delivery: EmailDelivery, *,
                          worker_id: str, code: str, message: str) -> None:
    if delivery.lease_owner != worker_id or delivery.status != "sending":
        return
    delivery.status, delivery.cancelled_at = "cancelled", utc_now()
    delivery.lease_owner = delivery.lease_expires_at = None
    delivery.error_code, delivery.error_message = code, message
    await session.flush()
