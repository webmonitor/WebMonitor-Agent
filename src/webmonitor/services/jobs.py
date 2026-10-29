"""One claim protocol for every asynchronous unit of work.

Nothing outside this module constructs a `Job`: scheduling, analysis, preview, agent
turns and production collection all enqueue and claim through these helpers.
"""
import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.models import Job, utc_now

LEASE_SECONDS = 90
TERMINAL = frozenset({"succeeded", "failed", "cancelled", "discarded"})


def _attempt(number: int, status: str, *, error_code: str | None = None,
             retryable: bool = False) -> dict[str, Any]:
    now = utc_now().isoformat()
    return {"number": number, "status": status, "started_at": now,
            "finished_at": None if status == "running" else now,
            "error_code": error_code, "retryable": retryable}


async def enqueue(session: AsyncSession, *, user_id: UUID, kind: str, url: str | None = None,
                  spec: dict[str, Any] | None = None, conversation_id: UUID | None = None,
                  draft_id: UUID | None = None, revision: int | None = None,
                  monitor_id: UUID | None = None, available_at=None) -> Job:
    job = Job(user_id=user_id, kind=kind, status="queued", url=url, spec=spec,
              conversation_id=conversation_id, draft_id=draft_id, revision=revision,
              monitor_id=monitor_id, available_at=available_at or utc_now())
    session.add(job)
    await session.flush()
    return job


async def wait(job_id: UUID, *, timeout: float = 70.0) -> Job:
    """Poll a committed job in its own session; the caller's transaction stays open."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        async with get_session_factory()() as session:
            job = await session.get(Job, job_id)
            if job is not None and job.status in TERMINAL:
                if job.status == "succeeded":
                    return job
                raise DomainError(job.error_code or "job_failed", 409)
        if asyncio.get_running_loop().time() >= deadline:
            raise DomainError("job_timeout", 504)
        await asyncio.sleep(0.25)


async def claim(session: AsyncSession, *, kind: str, worker_id: str,
                condition=None) -> Job | None:
    """Claim one due job. An expired lease is reaped before anything is re-claimed."""
    now = utc_now()
    query = select(Job).where(
        Job.kind == kind,
        or_(and_(Job.status == "queued", Job.available_at <= now),
            and_(Job.status == "running", Job.lease_expires_at <= now)),
    )
    if condition is not None:
        query = query.where(condition)
    job = await session.scalar(query.order_by(Job.available_at, Job.created_at)
        .with_for_update(skip_locked=True).limit(1).execution_options(populate_existing=True))
    if job is None:
        return None
    if job.status == "running":
        await _reap(session, job, now)
        return None
    job.status = "running"
    job.lease_owner = worker_id
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    job.started_at = job.started_at or now
    job.attempt_count += 1
    job.attempts = list(job.attempts or []) + [_attempt(job.attempt_count, "running")]
    job.error_code = job.error_message = None
    await session.flush()
    return job


async def _reap(session: AsyncSession, job: Job, now) -> None:
    """A lease that expired without a terminal write is a failed attempt."""
    if job.kind == "production":
        from webmonitor.services import runs
        await runs.lease_expired(session, job)
        return
    job.attempts = [attempt if index != len(job.attempts) - 1 else
                    {**attempt, "status": "failed", "finished_at": now.isoformat(),
                     "error_code": "lease_expired", "retryable": True}
                    for index, attempt in enumerate(job.attempts or [])]
    job.error_code, job.error_message = "lease_expired", "Worker lease expired"
    if job.attempt_count < get_settings().max_attempts:
        job.status, job.available_at = "queued", now
        job.lease_owner = job.lease_expires_at = None
    else:
        job.status, job.finished_at = "failed", now
        job.lease_owner = job.lease_expires_at = None
    await session.flush()


async def renew(session: AsyncSession, job_id: UUID, worker_id: str) -> bool:
    job = await session.scalar(select(Job).where(Job.id == job_id)
        .with_for_update().execution_options(populate_existing=True))
    now = utc_now()
    if (job is None or job.status != "running" or job.lease_owner != worker_id
            or job.cancel_requested_at is not None):
        return False
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    await session.flush()
    return True


async def finish(session: AsyncSession, job: Job, status: str, *, result: dict | None = None,
                 error_code: str | None = None, error_message: str | None = None) -> None:
    now = utc_now()
    job.status = status
    job.finished_at = now
    job.lease_owner = job.lease_expires_at = None
    job.error_code, job.error_message = error_code, error_message
    if result is not None:
        job.result = result
    if job.attempts:
        job.attempts = [attempt if index != len(job.attempts) - 1 else
                        {**attempt, "status": status, "finished_at": now.isoformat(),
                         "error_code": error_code} for index, attempt in enumerate(job.attempts)]
    await session.flush()


async def requeue(session: AsyncSession, job: Job, *, error_code: str, delay: float) -> None:
    """Retain the attempt history and schedule the next try."""
    now = utc_now()
    job.status, job.available_at = "queued", now + timedelta(seconds=delay)
    job.lease_owner = job.lease_expires_at = None
    job.error_code, job.error_message = error_code, error_code.replace("_", " ")
    if job.attempts:
        job.attempts = [attempt if index != len(job.attempts) - 1 else
                        {**attempt, "status": "failed", "finished_at": now.isoformat(),
                         "error_code": error_code, "retryable": True}
                        for index, attempt in enumerate(job.attempts)]
    await session.flush()


async def discard(session: AsyncSession, job: Job) -> None:
    if job.status in TERMINAL:
        return
    await finish(session, job, "discarded")


async def cancel(session: AsyncSession, job: Job) -> None:
    """Queued work stops now; running work stops at its next lease check."""
    if job.status in TERMINAL:
        return
    job.cancel_requested_at = utc_now()
    if job.status == "queued":
        await finish(session, job, "cancelled", error_code="cancelled")


async def cancel_pending(session: AsyncSession, *, draft_id: UUID | None = None,
                         monitor_id: UUID | None = None) -> None:
    rows = []
    if draft_id is not None:
        rows += list((await session.scalars(select(Job).where(Job.draft_id == draft_id,
            Job.status.in_(("queued", "running"))).with_for_update())).all())
    if monitor_id is not None:
        rows += list((await session.scalars(select(Job).where(Job.monitor_id == monitor_id,
            Job.kind == "production", Job.status.in_(("queued", "running")))
            .with_for_update())).all())
    for job in rows:
        await cancel(session, job)
