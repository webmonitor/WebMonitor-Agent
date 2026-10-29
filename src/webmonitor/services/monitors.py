"""Monitor reads and the three user commands: pause, resume, run now."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Job, Monitor, Snapshot, User, utc_now
from webmonitor.schemas.api import MonitorDetail, MonitorView, Page, SnapshotRecord
from webmonitor.security.auth import CurrentUser, require_owner
from webmonitor.services import jobs

ACTIVE = ("queued", "running")


def monitor_view(monitor: Monitor) -> MonitorView:
    return MonitorView(id=monitor.id, name=monitor.name, url=monitor.url,
        status=monitor.status, collection_mode=monitor.collection_mode,
        spec_version=monitor.spec_version, interval_seconds=monitor.interval_seconds,
        timezone=monitor.timezone, baseline_status=monitor.baseline_status,
        health_status=monitor.health_status,
        notification_group_ids=list(monitor.notification_group_ids or []),
        next_run_at=monitor.next_run_at, last_success_at=monitor.last_success_at,
        last_failure_at=monitor.last_failure_at, created_at=monitor.created_at)


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
                        offset: int) -> Page[MonitorView]:
    query = select(Monitor)
    if user.role != "admin":
        query = query.where(Monitor.user_id == user.user_id)
    rows = (await session.scalars(query.order_by(Monitor.created_at.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[MonitorView](items=[monitor_view(row) for row in rows], total=total or 0)


async def read_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> MonitorDetail:
    monitor = await read_monitor_row(session, user, monitor_id)
    baseline = None
    if monitor.baseline_snapshot_id is not None:
        snapshot = await session.get(Snapshot, monitor.baseline_snapshot_id)
        baseline = snapshot_record(snapshot) if snapshot is not None else None
    return MonitorDetail(**monitor_view(monitor).model_dump(), spec=monitor.spec,
                         baseline=baseline)


async def pause_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Monitor:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.status != "paused":
        monitor.status, monitor.paused_at = "paused", utc_now()
        await jobs.cancel_pending(session, monitor_id=monitor.id)
        await session.flush()
    return monitor


async def resume_monitor(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Monitor:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.status == "active":
        return monitor
    await session.execute(select(User.id).where(User.id == monitor.user_id).with_for_update())
    active = await session.scalar(select(func.count()).select_from(Monitor).where(
        Monitor.user_id == monitor.user_id, Monitor.status == "active"))
    if (active or 0) >= get_settings().max_active_monitors:
        raise DomainError("quota_exceeded", 409)
    monitor.status, monitor.paused_at, monitor.next_run_at = "active", None, utc_now()
    await session.flush()
    return monitor


async def enqueue_manual(session: AsyncSession, user: CurrentUser, monitor_id: UUID) -> Job:
    monitor = await read_monitor_row(session, user, monitor_id, lock=True)
    if monitor.status != "active":
        raise DomainError("monitor_not_active", 409)
    existing = await session.scalar(select(Job).where(Job.monitor_id == monitor.id,
        Job.kind == "production", Job.status.in_(ACTIVE)))
    if existing is not None:
        return existing
    return await jobs.enqueue(session, user_id=monitor.user_id, kind="production",
        monitor_id=monitor.id, url=monitor.url, spec=monitor.spec,
        revision=monitor.spec_version)


async def list_monitor_jobs(session: AsyncSession, user: CurrentUser, monitor_id: UUID,
                            limit: int, offset: int) -> Page:
    monitor = await read_monitor_row(session, user, monitor_id)
    query = select(Job).where(Job.monitor_id == monitor.id, Job.kind == "production")
    rows = (await session.scalars(query.order_by(Job.created_at.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    from webmonitor.services.conversations import job_view
    return Page(items=[job_view(row) for row in rows], total=total or 0)
