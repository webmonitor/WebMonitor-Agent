"""Notification groups, recipient resolution and leased notification delivery."""
import json
from datetime import UTC, datetime, time, timedelta
from email.utils import parseaddr
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import (
    Delivery,
    Event,
    Monitor,
    NotificationGroup,
    User,
    utc_now,
)
from webmonitor.notifications.delivery import send_email
from webmonitor.notifications.errors import DeliveryFailure
from webmonitor.notifications.rendering import render_email
from webmonitor.notifications.webhook import send_webhook
from webmonitor.schemas.api import Delivery as DeliveryView
from webmonitor.schemas.api import Group, MemberSpec, Page
from webmonitor.schemas.notifications import NotificationTestResult
from webmonitor.schemas.templates import EmailTemplateConfig
from webmonitor.security.auth import CurrentUser, require_admin
from webmonitor.security.egress import validate_webhook_url
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


def _message_id(delivery_id: UUID) -> str:
    domain = parseaddr(get_settings().mail_from)[1].split("@")[-1] or "webmonitor.local"
    return f"<{delivery_id}@{domain}>"


def _test_failure(exc: DeliveryFailure) -> DomainError:
    # Transport errors are already scrubbed of server text and credentials.
    return DomainError(exc.code, 502, exc.message)


async def send_test_email(user: CurrentUser, recipient: str) -> NotificationTestResult:
    """Send one explicit test without creating a monitor event or queued delivery."""
    require_admin(user)
    delivery = SimpleNamespace(recipient=recipient, message_id=_message_id(uuid4()))
    rendered = {
        "subject": "WebMonitor test notification",
        "text": "This is a test email from WebMonitor. No monitoring event was created.",
        "html": "<p>This is a test email from WebMonitor. No monitoring event was created.</p>",
    }
    try:
        response_code = await send_email(delivery, rendered)
    except DeliveryFailure as exc:
        raise _test_failure(exc) from None
    return NotificationTestResult(channel="email", response_code=response_code)


async def send_test_webhook(user: CurrentUser, url: str) -> NotificationTestResult:
    """POST a clearly marked test body through normal URL checks and signing."""
    require_admin(user)
    url = validate_webhook_url(url)
    delivery_id = uuid4()
    payload = {"test": True, "message": "This is a test webhook from WebMonitor."}
    delivery = SimpleNamespace(
        id=delivery_id,
        recipient=url,
        payload=payload,
        body_text=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    try:
        response_code = await send_webhook(delivery)
    except DeliveryFailure as exc:
        raise _test_failure(exc) from None
    return NotificationTestResult(channel="webhook", response_code=response_code)


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


def _quiet_time(value: datetime, zone_name: str, quiet_hours: dict[str, str]) -> datetime:
    """Return the first allowed instant, using the monitor's actual DST rules."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    zone = ZoneInfo(zone_name)
    local = value.astimezone(zone)
    start_hour, start_minute = (int(part) for part in quiet_hours['start'].split(':'))
    end_hour, end_minute = (int(part) for part in quiet_hours['end'].split(':'))
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    minute = local.hour * 60 + local.minute
    crosses_midnight = start > end
    is_quiet = ((start <= minute < end) if not crosses_midnight
                else (minute >= start or minute < end))
    if not is_quiet:
        return value
    end_date = local.date()
    if crosses_midnight and minute >= start:
        end_date += timedelta(days=1)
    wall_end = datetime.combine(end_date, time(end_hour, end_minute))
    valid = []
    for fold in (0, 1):
        candidate = wall_end.replace(tzinfo=zone, fold=fold)
        utc = candidate.astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None) == wall_end:
            valid.append(utc)
    if valid:
        # During a repeated wall time, use the first end that has not already passed.
        return next((candidate for candidate in sorted(valid) if candidate >= value), value)
    # A nonexistent wall time is moved forward by the zone's DST transition.
    return wall_end.replace(tzinfo=zone, fold=0).astimezone(UTC)


async def _event_available_at(session: AsyncSession, monitor: Monitor, event: Event) -> datetime:
    available_at = event.created_at
    if available_at.tzinfo is None:
        available_at = available_at.replace(tzinfo=UTC)
    cooldown = monitor.notification_cooldown_seconds or 0
    if cooldown:
        latest = await session.scalar(select(func.max(Delivery.available_at)).where(
            Delivery.monitor_id == monitor.id))
        if latest is not None:
            available_at = max(available_at, latest + timedelta(seconds=cooldown))
    if monitor.quiet_hours:
        available_at = _quiet_time(available_at, _timezone(monitor), monitor.quiet_hours)
    return available_at


async def enqueue_event_deliveries(session: AsyncSession, monitor: Monitor, event: Event,
                                   fields: dict) -> None:
    """Flush only. Disabled or empty routes never undo a valid snapshot."""
    payload = _payload(monitor, event, fields)
    event.payload = payload
    available_at = await _event_available_at(session, monitor, event)
    route = (monitor.event_channels or {}).get(event.type, monitor.delivery_channel)
    if route in ("webhook", "both"):
        if not monitor.webhook_url:
            raise DomainError("webhook_url_missing", 409)
        delivery_id = uuid4()
        subject = f"{monitor.name} · {event.type}"
        session.add(Delivery(id=delivery_id, user_id=monitor.user_id,
            monitor_id=monitor.id, event_id=event.id, channel="webhook",
            recipient=monitor.webhook_url, subject=subject, html="",
            body_text=json.dumps(payload, ensure_ascii=False, indent=2),
            payload={**payload, "channel": "webhook"},
            status="queued", attempt_count=0, available_at=available_at))
        await session.flush()
        if route == "webhook":
            return
    recipients = await approved_recipients(session, monitor)
    if not recipients:
        raise DomainError("notification_recipients_empty", 409)
    template = None
    if monitor.email_template is not None:
        if not isinstance(monitor.email_template, dict):
            raise DomainError("template_unavailable", 409)
        try:
            # Publication freezes {id, name, config}; production never resolves
            # the original row, so edits and soft deletion cannot change this mail.
            template = EmailTemplateConfig.model_validate(monitor.email_template.get("config"))
        except ValueError:
            # A frozen snapshot that no longer parses stays inert; the snapshot itself
            # is still the valid record of what the monitor was approved with.
            raise DomainError("template_unavailable", 409) from None
    rendered = render_email(event.type, payload, template)
    for recipient in recipients:
        delivery_id = uuid4()
        session.add(Delivery(id=delivery_id, user_id=monitor.user_id,
            monitor_id=monitor.id, event_id=event.id, channel="email",
            recipient=recipient["email"],
            subject=rendered["subject"], html=rendered["html"], body_text=rendered["text"],
            payload={**payload, "recipient_sources": recipient["group_ids"]},
            status="queued", attempt_count=0,
            available_at=available_at, message_id=_message_id(delivery_id)))
    await session.flush()


async def claim_delivery(session: AsyncSession, worker_id: str) -> Delivery | None:
    now = utc_now()
    delivery = await session.scalar(select(Delivery).where(
        Delivery.available_at <= now,
        or_(Delivery.status.in_(("queued", "retrying")),
            and_(Delivery.status == "sending",
                 Delivery.lease_expires_at <= now)),
    ).order_by(Delivery.available_at, Delivery.created_at)
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


async def authorized(session: AsyncSession, delivery: Delivery) -> bool:
    """Only this monitor's approved, still-active route authorizes a queued delivery."""
    monitor = await session.get(Monitor, delivery.monitor_id)
    if monitor is None:
        return False
    event_type = ((delivery.payload or {}).get("event") or {}).get("type")
    route = (monitor.event_channels or {}).get(event_type, monitor.delivery_channel)
    allowed = ("email", "webhook") if route == "both" else (route,)
    if delivery.channel not in allowed:
        return False
    if await session.scalar(select(User.active).where(User.id == delivery.user_id)) is not True:
        return False
    if delivery.channel == "webhook":
        return bool(monitor.webhook_url) and monitor.webhook_url == delivery.recipient
    sources = set((delivery.payload or {}).get("recipient_sources") or [])
    if not sources:
        return False
    recipients = await approved_recipients(session, monitor)
    return any(recipient["email"] == delivery.recipient
               and sources.intersection(recipient["group_ids"]) for recipient in recipients)


async def finish_delivery(session: AsyncSession, delivery: Delivery, *, worker_id: str,
                          failure=None, response_code: int | None = None) -> None:
    if delivery.lease_owner != worker_id or delivery.status != "sending":
        return
    now = utc_now()
    delivery.lease_owner = delivery.lease_expires_at = None
    delivery.response_code = getattr(failure, "response_code", None) if failure else response_code
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


async def cancel_delivery(session: AsyncSession, delivery: Delivery, *,
                          worker_id: str, code: str, message: str) -> None:
    if delivery.lease_owner != worker_id or delivery.status != "sending":
        return
    delivery.status, delivery.cancelled_at = "cancelled", utc_now()
    delivery.lease_owner = delivery.lease_expires_at = None
    delivery.error_code, delivery.error_message = code, message
    await session.flush()


def delivery_view(
    row: Delivery, monitor_name: str = "", *, include_recipient: bool = True
) -> DeliveryView:
    recipient = row.recipient if include_recipient or row.channel == "webhook" else None
    return DeliveryView(
        id=row.id,
        monitor_id=row.monitor_id,
        monitor_name=monitor_name,
        event_id=row.event_id,
        channel=row.channel,
        recipient=recipient,
        subject=row.subject,
        body_text=row.body_text,
        status=row.status,
        attempt_count=row.attempt_count,
        error_code=row.error_code,
        error_message=row.error_message,
        response_code=row.response_code,
        created_at=row.created_at,
        sent_at=row.sent_at,
        failed_at=row.failed_at,
    )


async def list_deliveries(
    session: AsyncSession,
    user: CurrentUser,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    monitor_id: UUID | None = None,
) -> Page[DeliveryView]:
    query = select(Delivery)
    if user.role != "admin":
        query = query.where(Delivery.user_id == user.user_id)
    if status is not None:
        query = query.where(Delivery.status == status)
    if monitor_id is not None:
        query = query.where(Delivery.monitor_id == monitor_id)
    rows = (
        await session.scalars(
            query.order_by(Delivery.created_at.desc(), Delivery.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    names = (
        {
            row.id: row.name
            for row in (
                await session.scalars(
                    select(Monitor).where(Monitor.id.in_({row.monitor_id for row in rows}))
                )
            ).all()
        }
        if rows
        else {}
    )
    include_recipient = user.role == "admin"
    return Page[DeliveryView](
        items=[
            delivery_view(row, names.get(row.monitor_id, ""), include_recipient=include_recipient)
            for row in rows
        ],
        total=total or 0,
    )


async def retry_delivery(
    session: AsyncSession, user: CurrentUser, delivery_id: UUID
) -> DeliveryView:
    row = await session.get(Delivery, delivery_id, with_for_update=True, populate_existing=True)
    if row is None or (row.user_id != user.user_id and user.role != "admin"):
        raise DomainError("not_found", 404)
    if row.status not in ("failed", "cancelled"):
        raise DomainError("delivery_not_retryable", 409, details={"status": row.status})
    row.status, row.available_at = "queued", utc_now()
    row.attempt_count = 0
    row.lease_owner = row.lease_expires_at = None
    row.error_code = row.error_message = row.response_code = None
    row.failed_at = row.cancelled_at = None
    await session.flush()
    monitor = await session.get(Monitor, row.monitor_id)
    return delivery_view(
        row,
        monitor.name if monitor is not None else "",
        include_recipient=user.role == "admin",
    )
