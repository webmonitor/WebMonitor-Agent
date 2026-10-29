"""The single process that runs scheduling, collection, agent turns and mail.

Each loop claims work with `FOR UPDATE SKIP LOCKED`, keeps the lease alive while doing
network or S3 I/O outside any transaction, and stops local work the moment the lease
can no longer be proven.
"""
import asyncio
import contextlib
import logging
import os
import socket
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.agent.orchestration import execute_job as execute_agent_job
from webmonitor.collection.browser import collect_browser
from webmonitor.collection.http import collect_http
from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.models import Draft, EmailDelivery, Job
from webmonitor.notifications.delivery import SendFailure, send_email
from webmonitor.schemas.monitors import DraftSpec
from webmonitor.services import drafts, jobs, notifications, runs
from webmonitor.storage.evidence import upload_evidence

logger = logging.getLogger(__name__)

RENEW_SECONDS = 15
COLLECTION_RETRYABLE = frozenset({"lease_expired", "collection_timeout", "target_unavailable",
                                  "storage_unavailable", "browser_collection_failed"})


def make_worker_id() -> str:
    return f"worker:{socket.gethostname()}:{os.getpid()}:{uuid4()}"[:200]


@asynccontextmanager
async def _session():
    async with get_session_factory()() as session:
        yield session


async def _locked(session: AsyncSession, job_id: UUID) -> Job | None:
    return await session.scalar(select(Job).where(Job.id == job_id).with_for_update()
        .execution_options(populate_existing=True))


def _owned(job: Job | None, worker_id: str) -> bool:
    return (job is not None and job.status == "running" and job.lease_owner == worker_id
            and job.cancel_requested_at is None)


async def _renew(job_id: UUID, worker_id: str, task: asyncio.Task) -> None:
    try:
        while True:
            await asyncio.sleep(RENEW_SECONDS)
            async with _session() as session:
                alive = await jobs.renew(session, job_id, worker_id)
                await session.commit()
            if not alive:
                task.cancel()
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        # Without a verified lease the work must stop; durable state stays recoverable.
        task.cancel()


def _prefix(job: Job) -> str:
    if job.kind == "production":
        return f"monitors/{job.monitor_id}/{job.id}"
    if job.kind == "preview":
        return f"drafts/{job.draft_id}/{job.id}"
    return f"analysis/{job.id}"


async def _collect(job_id: UUID, worker_id: str) -> None:
    async with _session() as session:
        job = await session.get(Job, job_id)
        if not _owned(job, worker_id):
            return
        kind, url, stored = job.kind, job.url, job.spec
    spec = (DraftSpec.model_validate(stored)
            if kind in ("preview", "production") and stored else None)
    mode = (stored or {}).get("collection_mode", "http")
    collector = collect_browser if mode == "browser" else collect_http
    current = asyncio.current_task()
    renewal = asyncio.create_task(_renew(job_id, worker_id, current))
    try:
        result = await collector(url, spec)
        refs = []
        for evidence_kind, data in (("html", result.html.encode("utf-8")),
                                    ("screenshot", result.screenshot)):
            if data is not None:
                refs.append(await upload_evidence(prefix=_prefix(job), kind=evidence_kind,
                                                  data=data))
        payload = {"final_url": result.final_url, "fields": result.fields,
                   "coverage": result.coverage, "evidence_refs": refs,
                   "duration_ms": result.duration_ms, "warnings": result.warnings,
                   "analysis": result.analysis}
        async with _session() as session, session.begin():
            live = await _locked(session, job_id)
            if not _owned(live, worker_id):
                return
            if live.kind == "production":
                await runs.commit_success(session, live, payload)
            else:
                live.result = payload
                if live.kind == "preview":
                    draft = await session.get(Draft, live.draft_id,
                                              with_for_update=True, populate_existing=True)
                    if draft is None:
                        raise DomainError("draft_missing", 409)
                    await drafts.build_preview(session, draft, live)
                await jobs.finish(session, live, "succeeded", result=payload)
    except asyncio.CancelledError:
        async with _session() as session, session.begin():
            live = await _locked(session, job_id)
            if _owned(live, worker_id):
                await jobs.finish(session, live, "cancelled",
                                  error_code="collection_cancelled")
        raise
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else "collection_failed"
        details = exc.details if isinstance(exc, DomainError) else {}
        await _fail(job_id, worker_id, code=code, details=details)
    finally:
        renewal.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await renewal


async def _fail(job_id: UUID, worker_id: str, *, code: str, details: dict) -> None:
    async with _session() as session, session.begin():
        live = await _locked(session, job_id)
        if not _owned(live, worker_id):
            return
        if live.kind == "production":
            await runs.fail_run(session, live, error_code=code,
                                error_message=code.replace("_", " "),
                                retryable=True, details=details)
            return
        retryable = code in COLLECTION_RETRYABLE or (
            code == "target_http_error" and int(details.get("status_code", 0)) >= 500)
        if retryable and live.attempt_count < get_settings().max_attempts:
            await jobs.requeue(session, live, error_code=code,
                               delay=1 if live.attempt_count == 1 else 5)
        else:
            await jobs.finish(session, live, "failed", error_code=code,
                              error_message=code.replace("_", " "))


async def scheduler_loop() -> None:
    while True:
        started = asyncio.get_running_loop().time()
        try:
            async with _session() as session, session.begin():
                await runs.schedule_due(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Scheduler tick failed")
        await asyncio.sleep(max(0.0, 1 - (asyncio.get_running_loop().time() - started)))


async def _agent_slot(worker_id: str) -> None:
    while True:
        job_id = None
        try:
            async with _session() as session, session.begin():
                job = await jobs.claim(session, kind="agent", worker_id=worker_id)
                job_id = job.id if job is not None else None
            if job_id is None:
                await asyncio.sleep(1)
                continue
            execution = asyncio.create_task(execute_agent_job(job_id, worker_id))
            renewal = asyncio.create_task(_renew(job_id, worker_id, execution))
            try:
                await execution
            finally:
                renewal.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await renewal
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Agent slot iteration failed; durable state retained")
            await asyncio.sleep(2)


async def _collection_slot(worker_id: str, mode: str) -> None:
    while True:
        job_id = None
        try:
            condition = Job.spec["collection_mode"].astext == mode
            async with _session() as session, session.begin():
                job = None
                for kind in ("production", "preview", "analyze"):
                    job = await jobs.claim(session, kind=kind, worker_id=worker_id,
                                           condition=condition)
                    if job is not None:
                        break
                job_id = job.id if job is not None else None
            if job_id is None:
                await asyncio.sleep(1)
                continue
            await _collect(job_id, worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Collection slot iteration failed")
            await asyncio.sleep(2)


async def _mailer_slot(worker_id: str) -> None:
    while True:
        try:
            async with _session() as session, session.begin():
                delivery = await notifications.claim_delivery(session, worker_id)
            if delivery is None:
                await asyncio.sleep(1)
                continue
            await _deliver(delivery, worker_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Mail delivery iteration failed")
            await asyncio.sleep(5)


async def _deliver(delivery: EmailDelivery, worker_id: str) -> None:
    delivery_id = delivery.id
    async with _session() as session:
        allowed = await notifications.authorized(session, delivery)
    if not allowed:
        async with _session() as session, session.begin():
            live = await session.get(EmailDelivery, delivery_id,
                                     with_for_update=True, populate_existing=True)
            await notifications.cancel_delivery(session, live, worker_id=worker_id,
                code="recipient_authorization_revoked",
                message="All recipient sources were revoked")
        return
    rendered = {"subject": delivery.subject, "html": delivery.html, "text": delivery.body_text}
    failure = None
    code = None
    try:
        code = await send_email(delivery, rendered)
    except SendFailure as exc:
        failure = exc
    async with _session() as session, session.begin():
        live = await session.get(EmailDelivery, delivery_id, with_for_update=True,
                                 populate_existing=True)
        await notifications.finish_delivery(session, live, worker_id=worker_id,
                                            failure=failure, response_code=code)


async def agent_loop(worker_id: str) -> None:
    settings = get_settings()
    await asyncio.gather(*[_agent_slot(f"{worker_id}:agent:{index}")
                           for index in range(settings.agent_concurrency)])


async def collection_loop(worker_id: str, mode: str) -> None:
    settings = get_settings()
    concurrency = settings.browser_concurrency if mode == "browser" else settings.http_concurrency
    await asyncio.gather(*[_collection_slot(f"{worker_id}:{mode}:{index}", mode)
                           for index in range(concurrency)])


async def mailer_loop(worker_id: str) -> None:
    await _mailer_slot(f"{worker_id}:mail")


async def run_worker() -> None:
    """Scheduler, agent, both collectors and the mailer in one process."""
    worker_id = make_worker_id()
    await asyncio.gather(
        scheduler_loop(),
        agent_loop(worker_id),
        collection_loop(worker_id, "http"),
        collection_loop(worker_id, "browser"),
        mailer_loop(worker_id),
    )
