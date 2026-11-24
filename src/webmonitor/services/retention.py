"""Bounded retention GC with S3 deletes outside database transactions.

Terminal deliveries and delivery-free events are reaped before snapshots and jobs.
Baseline and still-referenced event snapshots are not ordinary retention candidates.
A candidate is removed only after every unshared evidence object was deleted. Any
storage failure leaves all of its database references intact for the next pass.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Delivery, Draft, Event, Job, Monitor, Snapshot, utc_now
from webmonitor.storage.evidence import delete_evidence

TERMINAL_JOB_STATUSES = ("succeeded", "failed", "cancelled", "discarded")
TERMINAL_DELIVERY_STATUSES = ("sent", "failed", "cancelled")


@dataclass
class RetentionStats:
    deliveries_deleted: int = 0
    events_deleted: int = 0
    snapshots_deleted: int = 0
    jobs_deleted: int = 0
    evidence_deleted: int = 0
    failures: int = 0


@dataclass
class _Candidate:
    snapshot_id: UUID | None = None
    job_id: UUID | None = None
    refs: set[tuple[str, str]] = field(default_factory=set)


def _refs(snapshot: Snapshot | None = None, job: Job | None = None) -> set[tuple[str, str]]:
    sources = [snapshot.evidence_refs if snapshot is not None else []]
    if job is not None and isinstance(job.result, dict):
        sources.append(job.result.get("evidence_refs") or [])
    refs = set()
    for source in sources:
        for ref in source or []:
            if not isinstance(ref, dict):
                continue
            bucket, key = ref.get("bucket"), ref.get("object_key")
            if isinstance(bucket, str) and bucket and isinstance(key, str) and key:
                refs.add((bucket, key))
    return refs


def _old_terminal_jobs(cutoff: datetime):
    return Job.status.in_(TERMINAL_JOB_STATUSES), Job.finished_at <= cutoff


async def _candidates(session: AsyncSession, cutoff: datetime, limit: int) -> list[_Candidate]:
    """Select at most limit units; a production snapshot and its job are one unit."""
    snapshots = list((await session.scalars(select(Snapshot).where(
        Snapshot.collected_at <= cutoff,
        ~exists().where(Monitor.baseline_snapshot_id == Snapshot.id),
        ~exists().where(Event.snapshot_id == Snapshot.id),
    ).order_by(Snapshot.collected_at, Snapshot.id).limit(limit)
        .with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
    snapshots_by_job = {snapshot.job_id: snapshot for snapshot in snapshots}
    paired = []
    if snapshots_by_job:
        paired = list((await session.scalars(select(Job).where(
            Job.id.in_(snapshots_by_job), *_old_terminal_jobs(cutoff),
            ~exists().where(Event.job_id == Job.id),
        ).with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
    paired_by_id = {job.id: job for job in paired}
    candidates = []
    for snapshot in snapshots:
        job = paired_by_id.get(snapshot.job_id)
        candidates.append(_Candidate(snapshot.id, job.id if job else None,
                                     _refs(snapshot, job)))

    remaining = limit - len(candidates)
    if remaining:
        jobs = list((await session.scalars(select(Job).where(
            *_old_terminal_jobs(cutoff),
            ~exists().where(Snapshot.job_id == Job.id),
            ~exists().where(Event.job_id == Job.id),
        ).order_by(Job.finished_at, Job.id).limit(remaining)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
        candidates.extend(_Candidate(job_id=job.id, refs=_refs(job=job)) for job in jobs)
    return candidates


def _groups(candidates: list[_Candidate]) -> list[list[_Candidate]]:
    """Shared evidence makes candidates one all-or-nothing deletion group."""
    parents = list(range(len(candidates)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    owners = {}
    for index, candidate in enumerate(candidates):
        for ref in candidate.refs:
            other = owners.setdefault(ref, index)
            left, right = root(index), root(other)
            if left != right:
                parents[right] = left
    grouped = {}
    for index, candidate in enumerate(candidates):
        grouped.setdefault(root(index), []).append(candidate)
    return list(grouped.values())


async def _externally_referenced(session: AsyncSession, group: list[_Candidate]) -> bool:
    snapshot_ids = [item.snapshot_id for item in group if item.snapshot_id is not None]
    job_ids = [item.job_id for item in group if item.job_id is not None]
    refs = set().union(*(item.refs for item in group)) if group else set()
    for bucket, key in sorted(refs):
        fragment = [{"bucket": bucket, "object_key": key}]
        snapshots = select(Snapshot.id).where(Snapshot.evidence_refs.contains(fragment))
        jobs = select(Job.id).where(Job.result.op("->")("evidence_refs").contains(fragment))
        if snapshot_ids:
            snapshots = snapshots.where(Snapshot.id.not_in(snapshot_ids))
        if job_ids:
            jobs = jobs.where(Job.id.not_in(job_ids))
        drafts = select(Draft.id).where(
            Draft.extraction_preview.op("->")("evidence_refs").contains(fragment))
        for query in (snapshots, jobs, drafts):
            if await session.scalar(query.limit(1)) is not None:
                return True
    return False


async def collect(session: AsyncSession, *, now: datetime | None = None) -> RetentionStats:
    """Run one bounded pass; RETENTION_DAYS=0 disables retention entirely."""
    settings = get_settings()
    stats = RetentionStats()
    if settings.retention_days == 0:
        return stats
    cutoff = (now or utc_now()) - timedelta(days=settings.retention_days)
    limit = settings.retention_gc_batch_size
    delivery_finished = func.coalesce(Delivery.sent_at, Delivery.failed_at,
                                      Delivery.cancelled_at, Delivery.created_at)
    async with session.begin():
        deliveries = list((await session.scalars(select(Delivery).where(
            Delivery.status.in_(TERMINAL_DELIVERY_STATUSES), delivery_finished <= cutoff,
        ).order_by(delivery_finished, Delivery.id).limit(limit)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
        for delivery in deliveries:
            await session.delete(delivery)
        stats.deliveries_deleted = len(deliveries)

    remaining = limit - stats.deliveries_deleted
    if remaining:
        async with session.begin():
            events = list((await session.scalars(select(Event).where(
                Event.created_at <= cutoff,
                ~exists().where(Delivery.event_id == Event.id),
            ).order_by(Event.created_at, Event.id).limit(remaining)
                .with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
            for event in events:
                await session.delete(event)
            stats.events_deleted = len(events)

    remaining = limit - stats.deliveries_deleted - stats.events_deleted
    if not remaining:
        return stats
    async with session.begin():
        candidates = await _candidates(session, cutoff, remaining)
    if not candidates:
        return stats

    deletable = []
    for group in _groups(candidates):
        # Reference checks use a short transaction which ends before any S3 I/O.
        async with session.begin():
            protected = await _externally_referenced(session, group)
        if protected:
            continue
        refs = set().union(*(item.refs for item in group))
        failed = False
        for bucket, key in sorted(refs):
            try:
                await delete_evidence(bucket, key)
                stats.evidence_deleted += 1
            except DomainError:
                stats.failures += 1
                failed = True
                break
        if not failed:
            deletable.extend(group)

    if not deletable:
        return stats
    snapshot_ids = [item.snapshot_id for item in deletable if item.snapshot_id is not None]
    job_ids = [item.job_id for item in deletable if item.job_id is not None]
    async with session.begin():
        snapshots = []
        if snapshot_ids:
            snapshots = list((await session.scalars(select(Snapshot).where(
                Snapshot.id.in_(snapshot_ids), Snapshot.collected_at <= cutoff,
                ~exists().where(Monitor.baseline_snapshot_id == Snapshot.id),
                ~exists().where(Event.snapshot_id == Snapshot.id),
            ).with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
        for snapshot in snapshots:
            await session.delete(snapshot)
        await session.flush()
        jobs = []
        if job_ids:
            jobs = list((await session.scalars(select(Job).where(
                Job.id.in_(job_ids), *_old_terminal_jobs(cutoff),
                ~exists().where(Snapshot.job_id == Job.id),
                ~exists().where(Event.job_id == Job.id),
            ).with_for_update(skip_locked=True).execution_options(populate_existing=True))).all())
        for job in jobs:
            await session.delete(job)
        stats.snapshots_deleted = len(snapshots)
        stats.jobs_deleted = len(jobs)
    return stats
