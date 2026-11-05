"""The single process that runs scheduling, collection, agent turns and mail.

Each loop claims work with `FOR UPDATE SKIP LOCKED`, keeps the lease alive while doing
network or S3 I/O outside any transaction, and stops local work the moment the lease
can no longer be proven.
"""
import asyncio
import logging
import os
import socket
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.agent.orchestration import execute_job as execute_agent_job
from webmonitor.collection.api import collect_api
from webmonitor.collection.browser import collect_browser
from webmonitor.collection.http import collect_http
from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.models import Delivery, Draft, Job
from webmonitor.notifications.delivery import send_email
from webmonitor.notifications.errors import DeliveryFailure
from webmonitor.notifications.webhook import send_webhook
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.services import accounts, drafts, jobs, notifications, runs
from webmonitor.storage.evidence import delete_evidence, upload_evidence

logger = logging.getLogger(__name__)

RENEW_SECONDS = 15
SESSION_PURGE_SECONDS = 3600
COLLECTION_RETRYABLE = frozenset({"lease_expired", "collection_timeout", "target_unavailable",
                                  "storage_unavailable", "browser_collection_failed"})


def make_worker_id() -> str:
    return f"worker:{socket.gethostname()}:{os.getpid()}:{uuid4()}"[:200]


@asynccontextmanager
async def _session():
    async with get_session_factory()() as session:
        yield session


async def _locked(session: AsyncSession, job_id: UUID) -> Job | None:
    _, job = await jobs.lock(session, job_id)
    return job


def _owned(job: Job | None, worker_id: str, *, terminal: bool = False) -> bool:
    return (job is not None and job.status == "running" and job.lease_owner == worker_id
            and (terminal or job.cancel_requested_at is None))


async def _renew(job_id: UUID, worker_id: str, task: asyncio.Task) -> None:
    """Keep the lease alive; a transient database hiccup must not kill the work."""
    loop = asyncio.get_running_loop()
    last_ok = loop.time()
    try:
        while True:
            await asyncio.sleep(RENEW_SECONDS)
            try:
                async with _session() as session:
                    alive = await jobs.renew(session, job_id, worker_id)
                    await session.commit()
            except Exception:
                # The lease is still provable for one more window; retry inside it.
                if loop.time() - last_ok <= jobs.LEASE_SECONDS - RENEW_SECONDS:
                    logger.warning("Lease renewal failed; retrying", exc_info=True)
                    continue
                task.cancel()
                return
            if not alive:
                task.cancel()
                return
            last_ok = loop.time()
    except asyncio.CancelledError:
        raise


def _prefix(job: Job) -> str:
    if job.kind == "production":
        return f"monitors/{job.monitor_id}/{job.id}"
    if job.kind == "preview":
        return f"drafts/{job.draft_id}/{job.id}"
    return f"analysis/{job.id}"


async def _discard_evidence(refs: list[dict]) -> None:
    """Delete uploads that were never committed; the snapshot will not reference them."""
    for ref in refs:
        try:
            await delete_evidence(ref["bucket"], ref["object_key"])
        except Exception:
            logger.warning("Could not delete orphaned evidence %s", ref["object_key"],
                           exc_info=True)


async def _collect(job_id: UUID, worker_id: str) -> None:
    async with _session() as session, session.begin():
        job = await _locked(session, job_id)
        if not _owned(job, worker_id, terminal=True):
            return
        if job.cancel_requested_at is not None:
            await jobs.finish(session, job, "cancelled", error_code="collection_cancelled")
            return
        kind, url, stored = job.kind, job.url, job.spec
    spec = (MonitorSpec.model_validate(stored)
            if kind in ("preview", "production") and stored else None)
    mode = (stored or {}).get("collection_mode", "http")
    op = (stored or {}).get("op")
    current = asyncio.current_task()
    renewal = asyncio.create_task(_renew(job_id, worker_id, current))
    uploaded: list[dict] = []
    try:
        if op == "network":
            result = await collect_browser(url, network=True)
        elif spec is not None and spec.source is not None:
            result = await collect_api(url, spec)
        else:
            collector = collect_browser if mode == "browser" else collect_http
            result = await collector(url, spec)
        if result.body is not None:
            uploaded.append(await upload_evidence(prefix=_prefix(job), kind=result.body_kind,
                                                  data=result.body.encode("utf-8")))
        if result.screenshot is not None:
            uploaded.append(await upload_evidence(prefix=_prefix(job), kind="screenshot",
                                                  data=result.screenshot))
        payload = {"final_url": result.final_url, "fields": result.fields,
                   "coverage": result.coverage, "evidence_refs": uploaded,
                   "duration_ms": result.duration_ms, "warnings": result.warnings,
                   "analysis": result.analysis}
        async with _session() as session, session.begin():
            live = await _locked(session, job_id)
            if not _owned(live, worker_id, terminal=True):
                await _discard_evidence(uploaded)
                return
            if live.cancel_requested_at is not None:
                await _discard_evidence(uploaded)
                await jobs.finish(session, live, "cancelled", error_code="collection_cancelled")
                return
            if live.kind == "production":
                await runs.commit_success(session, live, payload)
            else:
                live.result = payload
                if live.kind == "preview":
                    draft = await session.get(Draft, live.draft_id,
                                              populate_existing=True)
                    if draft is None:
                        raise DomainError("draft_missing", 409)
                    await drafts.build_preview(session, draft, live)
                await jobs.finish(session, live, "succeeded", result=payload)
        # Committed: the rows now reference these objects.
        uploaded = []
    except asyncio.CancelledError:
        await _discard_evidence(uploaded)
        async with _session() as session, session.begin():
            live = await _locked(session, job_id)
            if _owned(live, worker_id, terminal=True):
                await jobs.finish(session, live, "cancelled",
                                  error_code="collection_cancelled")
        raise
    except Exception as exc:
        await _discard_evidence(uploaded)
        code = exc.code if isinstance(exc, DomainError) else "collection_failed"
        details = exc.details if isinstance(exc, DomainError) else {}
        await _fail(job_id, worker_id, code=code, details=details)
    finally:
        renewal.cancel()
        await asyncio.gather(renewal, return_exceptions=True)


async def _fail(job_id: UUID, worker_id: str, *, code: str, details: dict) -> None:
    async with _session() as session, session.begin():
        live = await _locked(session, job_id)
        if not _owned(live, worker_id, terminal=True):
            return
        if live.cancel_requested_at is not None:
            await jobs.finish(session, live, "cancelled", error_code="collection_cancelled")
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
    loop = asyncio.get_running_loop()
    purged_at = 0.0
    while True:
        started = loop.time()
        try:
            async with _session() as session, session.begin():
                await runs.schedule_due(session)
            if started - purged_at >= SESSION_PURGE_SECONDS:
                async with _session() as session, session.begin():
                    await accounts.purge_expired_sessions(session)
                purged_at = started
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler tick failed")
        await asyncio.sleep(max(0.0, 1 - (loop.time() - started)))


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
                await asyncio.gather(renewal, return_exceptions=True)
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
        except Exception:
            logger.exception("Agent slot iteration failed; durable state retained")
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
            execution = asyncio.create_task(_collect(job_id, worker_id))
            await execution
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
        except Exception:
            logger.exception("Collection slot iteration failed")
            await asyncio.sleep(2)


async def _delivery_slot(worker_id: str) -> None:
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
            logger.exception("Notification delivery iteration failed")
            await asyncio.sleep(5)


async def _deliver(delivery: Delivery, worker_id: str) -> None:
    delivery_id = delivery.id
    async with _session() as session:
        allowed = await notifications.authorized(session, delivery)
    if not allowed:
        async with _session() as session, session.begin():
            live = await session.get(Delivery, delivery_id,
                                     with_for_update=True, populate_existing=True)
            await notifications.cancel_delivery(session, live, worker_id=worker_id,
                code="recipient_authorization_revoked",
                message="The approved delivery route was revoked")
        return
    failure = None
    code = None
    try:
        if delivery.channel == "webhook":
            code = await send_webhook(delivery)
        else:
            rendered = {"subject": delivery.subject, "html": delivery.html,
                        "text": delivery.body_text}
            code = await send_email(delivery, rendered)
    except DeliveryFailure as exc:
        failure = exc
    except Exception:
        # An unexpected fault must still end this attempt, never leave it `sending`.
        logger.exception("Notification delivery aborted: delivery=%s", delivery_id)
        failure = DeliveryFailure("delivery_aborted", "Delivery aborted", retryable=False)
    try:
        async with _session() as session, session.begin():
            live = await session.get(Delivery, delivery_id, with_for_update=True,
                                     populate_existing=True)
            if live is None:
                return
            await notifications.finish_delivery(session, live, worker_id=worker_id,
                                                failure=failure, response_code=code)
    except Exception:
        # The lease expires and the row is claimed again; nothing is lost.
        logger.exception("Mail delivery result could not be stored: delivery=%s", delivery_id)


async def agent_loop(worker_id: str) -> None:
    settings = get_settings()
    await asyncio.gather(*[_agent_slot(f"{worker_id}:agent:{index}")
                           for index in range(settings.agent_concurrency)])


async def collection_loop(worker_id: str, mode: str) -> None:
    settings = get_settings()
    concurrency = settings.browser_concurrency if mode == "browser" else settings.http_concurrency
    await asyncio.gather(*[_collection_slot(f"{worker_id}:{mode}:{index}", mode)
                           for index in range(concurrency)])


async def delivery_loop(worker_id: str) -> None:
    await _delivery_slot(f"{worker_id}:delivery")


async def run_worker() -> None:
    """Scheduler, agent, both collectors and notification delivery in one process."""
    worker_id = make_worker_id()
    # One loop crashing takes the process down loudly instead of running half-deaf.
    async with asyncio.TaskGroup() as group:
        group.create_task(scheduler_loop())
        group.create_task(agent_loop(worker_id))
        group.create_task(collection_loop(worker_id, "http"))
        group.create_task(collection_loop(worker_id, "browser"))
        group.create_task(delivery_loop(worker_id))
