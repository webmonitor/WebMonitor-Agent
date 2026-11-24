"""Monitor reads and the three user commands: pause, resume, run now."""
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Draft, Job, Monitor, Snapshot, User, utc_now
from webmonitor.schemas.api import (
    DerivedDraft,
    MonitorBulkItemResult,
    MonitorBulkResult,
    MonitorBulkUpdate,
    MonitorCommandError,
    MonitorDetail,
    MonitorSpecDocument,
    MonitorTagsUpdate,
    MonitorView,
    Page,
    SnapshotDetail,
    SnapshotRecord,
    SpecVersion,
)
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.schemas.monitors import MonitorSpec, content_hash
from webmonitor.security.auth import CurrentUser, require_owner
from webmonitor.security.egress import validate_webhook_url
from webmonitor.services import drafts, jobs, notifications

ACTIVE = ("queued", "running")


def monitor_view(monitor: Monitor) -> MonitorView:
    return MonitorView(id=monitor.id, name=monitor.name, url=monitor.url,
        status=monitor.status, collection_mode=monitor.collection_mode,
        spec_version=monitor.spec_version, interval_seconds=monitor.interval_seconds,
        timezone=monitor.timezone, baseline_status=monitor.baseline_status,
        health_status=monitor.health_status, tags=list(monitor.tags or []),
        notification_group_ids=list(monitor.notification_group_ids or []),
        notification_cooldown_seconds=monitor.notification_cooldown_seconds,
        quiet_hours=monitor.quiet_hours,
        delivery_channel=monitor.delivery_channel,
        event_channels=dict(monitor.event_channels or {}),
        webhook_url=monitor.webhook_url,
        email_template_id=monitor.email_template_id,
        next_run_at=monitor.next_run_at, last_success_at=monitor.last_success_at,
        last_failure_at=monitor.last_failure_at, created_at=monitor.created_at,
        archived_at=monitor.archived_at)


def snapshot_record(snapshot: Snapshot) -> SnapshotRecord:
    return SnapshotRecord(id=snapshot.id, job_id=snapshot.job_id,
        spec_version=snapshot.spec_version, final_url=snapshot.final_url,
        extracted_data=snapshot.extracted_data, coverage=snapshot.coverage,
        evidence_refs=list(snapshot.evidence_refs or []), collected_at=snapshot.collected_at)


async def read_monitor_row(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                           *, lock: bool = False) -> Monitor:
    query = select(Monitor).where(Monitor.id == monitor_id)
    if lock:
        query = query.with_for_update()
    return require_owner(user, await session.scalar(
        query.execution_options(populate_existing=True)))


async def list_monitors(session: AsyncSession, user: CurrentUser, limit: int,
                        offset: int, *, archived: bool = False, keyword: str | None = None,
                        health_status: str | None = None, status: str | None = None,
                        tags: list[str] | None = None) -> Page[MonitorView]:
    conditions = [Monitor.archived_at.is_not(None) if archived
                  else Monitor.archived_at.is_(None)]
    if user.role != "admin":
        conditions.append(Monitor.user_id == user.user_id)
    if keyword and keyword.strip():
        term = keyword.strip().lower()
        conditions.append(or_(func.lower(Monitor.name).contains(term, autoescape=True),
                              func.lower(Monitor.url).contains(term, autoescape=True)))
    if health_status is not None:
        conditions.append(Monitor.health_status == health_status)
    if status is not None:
        conditions.append(Monitor.status == status)
    for tag in tags or []:
        conditions.append(Monitor.tags.contains([tag]))
    query = select(Monitor).where(*conditions)
    rows = (await session.scalars(query.order_by(Monitor.created_at.desc(), Monitor.id.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(Monitor).where(*conditions))
    return Page[MonitorView](items=[monitor_view(row) for row in rows], total=total or 0)


async def read_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> MonitorDetail:
    monitor = await read_monitor_row(session, user, monitor_id)
    baseline = None
    if monitor.baseline_snapshot_id is not None:
        snapshot = await session.get(Snapshot, monitor.baseline_snapshot_id)
        baseline = snapshot_record(snapshot) if snapshot is not None else None
    recipients = [item["email"] for item in monitor.approved_recipients or []
                  if isinstance(item, dict) and "email" in item]
    return MonitorDetail(**monitor_view(monitor).model_dump(), spec=monitor.spec,
        baseline=baseline, email_template=monitor.email_template,
        approved_recipients=recipients if user.role == "admin" else [],
        approved_recipient_count=len(recipients))


async def export_spec(session: AsyncSession, user: CurrentUser,
                      monitor_id: UUID) -> MonitorSpecDocument:
    monitor = await read_monitor_row(session, user, monitor_id)
    return MonitorSpecDocument(spec_version=monitor.spec_version,
        spec=MonitorSpec.model_validate(monitor.spec))


async def import_spec(session: AsyncSession, user: CurrentUser,
                      document: MonitorSpecDocument) -> DerivedDraft:
    """Import starts a normal draft; only its existing preview/approve flow can publish."""
    conversation = Conversation(user_id=user.user_id,
        title=f"Import: {document.spec.name}"[:200])
    session.add(conversation)
    await session.flush()
    draft = await drafts.save_spec(session, user, conversation_id=conversation.id,
                                   spec=document.spec)
    return DerivedDraft(conversation_id=conversation.id, draft_id=draft.id,
        spec_revision=draft.spec_revision, settings_revision=draft.settings_revision)


async def pause_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Monitor:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.status != "paused":
        monitor.status, monitor.paused_at = "paused", utc_now()
        await jobs.cancel_pending(session, monitor_id=monitor.id)
        await session.flush()
    return monitor


async def resume_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Monitor:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.archived_at is not None:
        raise DomainError("monitor_archived", 409)
    if monitor.status == "active":
        return monitor
    await session.execute(select(User.id).where(User.id == monitor.user_id).with_for_update())
    active = await session.scalar(select(func.count()).select_from(Monitor).where(
        Monitor.user_id == monitor.user_id, Monitor.status == "active",
        Monitor.archived_at.is_(None)))
    if (active or 0) >= get_settings().max_active_monitors:
        raise DomainError("quota_exceeded", 409)
    monitor.status, monitor.paused_at, monitor.next_run_at = "active", None, utc_now()
    await session.flush()
    return monitor


async def bulk_update(session: AsyncSession, user: CurrentUser,
                      payload: MonitorBulkUpdate) -> MonitorBulkResult:
    """Run the ordinary per-monitor command in a savepoint for every selected row."""
    results: list[MonitorBulkItemResult] = []
    for monitor_id in payload.monitor_ids:
        try:
            async with session.begin_nested():
                command = pause_monitor if payload.action == "pause" else resume_monitor
                monitor = await command(session, user, monitor_id)
                results.append(MonitorBulkItemResult(
                    monitor_id=monitor_id, ok=True, monitor=monitor_view(monitor)))
        except DomainError as exc:
            results.append(MonitorBulkItemResult(monitor_id=monitor_id, ok=False,
                error=MonitorCommandError(code=exc.code, message=exc.message)))
    return MonitorBulkResult(items=results)


async def enqueue_manual(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Job:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.status != "active":
        raise DomainError("monitor_not_active", 409)
    existing = await session.scalar(select(Job).where(Job.monitor_id == monitor.id,
        Job.kind == "production", Job.status.in_(ACTIVE)))
    if existing is not None:
        return existing
    await jobs.enforce_hourly_quota(session, user_id=monitor.user_id, kind="production",
                                    limit=get_settings().manual_runs_per_hour)
    return await jobs.enqueue(session, user_id=monitor.user_id, kind="production",
        monitor_id=monitor.id, url=monitor.url, spec=monitor.spec,
        revision=monitor.spec_version)


async def list_monitor_jobs(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                            limit: int, offset: int) -> Page:
    monitor = await read_monitor_row(session, user, monitor_id)
    query = select(Job).where(Job.monitor_id == monitor.id, Job.kind == "production")
    rows = (await session.scalars(query.order_by(Job.created_at.desc(), Job.id.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    from webmonitor.services.conversations import job_view
    return Page(items=[job_view(row) for row in rows], total=total or 0)


async def rename_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                         name: str) -> Monitor:
    """A name change is not a new collection contract, so the version is kept."""
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    spec = MonitorSpec.model_validate(monitor.spec).model_copy(update={"name": name.strip()})
    monitor.name = spec.name
    monitor.spec = spec.model_dump(mode="json")
    monitor.spec_hash = content_hash(spec)
    await session.flush()
    return monitor


async def update_tags(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                      payload: MonitorTagsUpdate) -> Monitor:
    """Organization metadata never changes the collection contract or its baseline."""
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    monitor.tags = payload.tags
    await session.flush()
    return monitor


async def update_delivery_settings(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                                    settings: DeliverySettings) -> Monitor:
    """Recipients, cadence and template, edited by hand on the monitor.

    The collection contract and the baseline are untouched: this is the one place
    delivery is configured, and the conversation never asks for it.
    """
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    schedule = settings.schedule
    missing = [name for name, absent in (
        ("notification_group_ids", settings.channel in ("email", "both")
         and not settings.notification_group_ids),
        ("webhook_url", settings.channel in ("webhook", "both") and not settings.webhook_url),
        ("schedule", schedule is None)) if absent]
    if missing or schedule is None:
        raise DomainError("settings_incomplete", 409, details={"missing": missing})
    spec = MonitorSpec.model_validate(monitor.spec)
    if settings.channel in ("webhook", "both"):
        validate_webhook_url(settings.webhook_url)
    if settings.channel == "webhook":
        recipients = []
        template_id, snapshot = monitor.email_template_id, monitor.email_template
    else:
        recipients = await notifications.load_recipients(
            session, settings.notification_group_ids, lock=True)
        template_id, snapshot = await drafts._template_snapshot(session, settings, spec)
    drafts._apply_settings(monitor, spec, settings, schedule, template_id, snapshot, recipients)
    await session.flush()
    return monitor


async def archive_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Monitor:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.archived_at is None:
        monitor.archived_at = utc_now()
        monitor.status = "paused"
        monitor.paused_at = monitor.paused_at or utc_now()
        await jobs.cancel_pending(session, monitor_id=monitor.id)
        await session.flush()
    return monitor


async def restore_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Monitor:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.archived_at is not None:
        monitor.archived_at = None
        await session.flush()
    return monitor


async def list_snapshots(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                         limit: int, offset: int) -> Page[SnapshotRecord]:
    monitor = await read_monitor_row(session, user, monitor_id)
    query = select(Snapshot).where(Snapshot.monitor_id == monitor.id)
    rows = (await session.scalars(query.order_by(Snapshot.collected_at.desc(),
        Snapshot.id.desc()).limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[SnapshotRecord](items=[snapshot_record(row) for row in rows], total=total or 0)


async def published_spec(session: AsyncSession, monitor_id: UUID, version: int) -> dict:
    """Resolve the immutable publication that produced a historical collection."""
    spec = await session.scalar(select(Draft.spec).where(
        Draft.monitor_id == monitor_id, Draft.published_spec_version == version))
    if spec is None:
        raise DomainError("not_found", 404)
    return spec


async def read_snapshot(session: AsyncSession, user: CurrentUser,
                        snapshot_id: UUID) -> SnapshotDetail:
    snapshot = await session.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise DomainError("not_found", 404)
    monitor = require_owner(user, await session.get(Monitor, snapshot.monitor_id))
    spec = await published_spec(session, monitor.id, snapshot.spec_version)
    return SnapshotDetail(**snapshot_record(snapshot).model_dump(),
        monitor_id=monitor.id, monitor_name=monitor.name, spec=spec)


async def list_spec_versions(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                             limit: int, offset: int) -> Page[SpecVersion]:
    """One row per publication that changed the collection contract."""
    monitor = await read_monitor_row(session, user, monitor_id)
    query = select(Draft).where(Draft.monitor_id == monitor.id,
                                Draft.published_spec_version.is_not(None))
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await session.scalars(query.order_by(Draft.published_spec_version.desc())
        .limit(limit).offset(offset))).all()
    return Page[SpecVersion](items=[
        SpecVersion(id=row.id, version=row.published_spec_version or 0,
            draft_id=row.id, spec=row.spec or {}, spec_hash=row.spec_hash or "",
            published_at=row.updated_at,
            current=row.published_spec_version == monitor.spec_version)
        for row in rows
    ], total=total)
