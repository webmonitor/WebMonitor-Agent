"""Production scheduling, fenced commits and retry policy.

Network and S3 I/O finish before these helpers run; every helper only flushes.
"""
import hashlib
import json
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.collection.diff import evaluate_rules
from webmonitor.collection.validation import validate_collection
from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Event, Job, Monitor, Snapshot, utc_now
from webmonitor.schemas.monitors import DraftSpec
from webmonitor.services import jobs, notifications

ACTIVE = ("queued", "running")
RETRYABLE = frozenset({"lease_expired", "collection_timeout", "target_unavailable",
                       "storage_unavailable", "browser_collection_failed"})
# A valid snapshot is never rolled back because notifications cannot be composed.
NOTIFICATION_ERRORS = frozenset({"notification_routes_invalid", "notification_recipients_empty",
                                 "template_unavailable", "template_contract_failed"})


async def schedule_due(session: AsyncSession, *, now=None, limit: int = 200) -> int:
    now = now or utc_now()
    due = (await session.scalars(select(Monitor).where(
        Monitor.status == "active", Monitor.next_run_at <= now)
        .order_by(Monitor.next_run_at, Monitor.id).limit(limit)
        .with_for_update(skip_locked=True).execution_options(populate_existing=True))).all()
    created = 0
    for monitor in due:
        busy = await session.scalar(select(Job.id).where(Job.monitor_id == monitor.id,
            Job.kind == "production", Job.status.in_(ACTIVE)))
        if busy is None:
            await jobs.enqueue(session, user_id=monitor.user_id, kind="production",
                monitor_id=monitor.id, url=monitor.url, spec=monitor.spec,
                revision=monitor.spec_version)
            created += 1
        # Late ticks merge; an overlapping tick is deliberately skipped.
        monitor.next_run_at = now + timedelta(seconds=monitor.interval_seconds)
    await session.flush()
    return created


async def _locked(session: AsyncSession, job_id: UUID) -> tuple[Monitor | None, Job]:
    monitor, job = await jobs.lock(session, job_id)
    return monitor, job


def _stale(monitor: Monitor | None, job: Job) -> bool:
    return (monitor is None or monitor.status != "active"
            or job.revision != monitor.spec_version)


def _field_labels(monitor: Monitor) -> dict[str, str]:
    """The readable name of each field travels with the event it explains."""
    try:
        spec = DraftSpec.model_validate(monitor.spec or {})
    except ValueError:
        return {}
    return {field.name: field.semantic for field in spec.fields}


ERROR_SUMMARIES = {
    "url_forbidden": "目标地址不在允许范围内",
    "target_unavailable": "目标页面无法访问",
    "target_http_error": "目标页面返回错误",
    "collection_timeout": "采集超时",
    "browser_unavailable": "浏览器环境不可用",
    "storage_unavailable": "证据存储暂时不可用",
    "lease_expired": "本次执行超时",
}


async def _event(session: AsyncSession, monitor: Monitor, job: Job, event_type: str, *,
                 before, after, summary: str, fields: dict,
                 snapshot_id: UUID | None = None, differences: list | None = None,
                 fingerprint: str | None = None) -> Event | None:
    event = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot_id,
        type=event_type, change={"before": before, "after": after, "summary": summary,
                                 "differences": differences or [],
                                 "labels": _field_labels(monitor)},
        failure_fingerprint=fingerprint)
    session.add(event)
    await session.flush()
    try:
        await notifications.enqueue_event_deliveries(session, monitor, event, fields)
    except DomainError as exc:
        if exc.code not in NOTIFICATION_ERRORS:
            raise
        event.payload = {"skipped": exc.code}
    return event


def _event_type(spec: DraftSpec, diff: dict) -> str:
    fields = {field.name: field for field in spec.fields}
    for rule in spec.change_rules.rules:
        if any(item["field"] == rule.field for item in diff["differences"]):
            kind = fields[rule.field].type
            return ("price_changed" if kind == "money"
                    else "list_changed" if kind == "list" else "content_changed")
    return "content_changed"


async def commit_success(session: AsyncSession, job: Job, result: dict) -> bool:
    """First success only establishes the baseline; later ones may publish events."""
    monitor, job = await _locked(session, job.id)
    now = utc_now()
    if job.status != "running" or job.cancel_requested_at is not None or _stale(monitor, job):
        await jobs.discard(session, job)
        return False
    spec = DraftSpec.model_validate(monitor.spec)
    baseline = await session.get(Snapshot, monitor.baseline_snapshot_id) \
        if monitor.baseline_snapshot_id else None
    previous = baseline.extracted_data if baseline else None
    fields, coverage = result["fields"], result["coverage"]
    validate_collection(spec, fields, previous=previous, coverage=coverage)
    diff = evaluate_rules(spec, previous, fields, monitor.rule_state or {})
    first_success = monitor.baseline_status == "pending_first_success"
    snapshot = Snapshot(monitor_id=monitor.id, job_id=job.id, spec_version=job.revision,
        final_url=result["final_url"], extracted_data=fields, coverage=coverage,
        rule_state=diff["rule_state"], evidence_refs=result.get("evidence_refs") or [],
        collected_at=now)
    session.add(snapshot)
    await session.flush()
    if not first_success:
        if monitor.health_status == "failed":
            await _event(session, monitor, job, "recovered", before=previous, after=fields,
                summary="采集已恢复", fields=fields, snapshot_id=snapshot.id,
                fingerprint=monitor.failure_fingerprint)
        if diff["triggered"]:
            summary = "; ".join(
                f"{item['field']}: {json.dumps(item['before'], ensure_ascii=False)} → "
                f"{json.dumps(item['after'], ensure_ascii=False)}"
                for item in diff["differences"])
            await _event(session, monitor, job, _event_type(spec, diff), before=previous,
                after=fields, summary=summary, fields=fields, snapshot_id=snapshot.id,
                differences=diff["differences"])
    monitor.baseline_snapshot_id = snapshot.id
    monitor.baseline_status = "ready"
    monitor.rule_state = diff["rule_state"]
    monitor.last_success_at = now
    monitor.health_status, monitor.failure_fingerprint = "healthy", None
    await jobs.finish(session, job, "succeeded", result=result)
    await session.flush()
    return True


async def fail_run(session: AsyncSession, job: Job, *, error_code: str,
                   error_message: str = "", retryable: bool = False,
                   details: dict | None = None) -> bool:
    monitor, job = await _locked(session, job.id)
    now = utc_now()
    if job.status not in ("running", "queued"):
        return False
    if job.cancel_requested_at is not None:
        await jobs.finish(session, job, "cancelled", error_code="collection_cancelled")
        return True
    if _stale(monitor, job):
        await jobs.discard(session, job)
        return True
    transient = error_code in RETRYABLE or (
        error_code == "target_http_error" and int((details or {}).get("status_code", 0)) >= 500)
    if retryable and transient and job.attempt_count < get_settings().max_attempts:
        await jobs.requeue(session, job, error_code=error_code,
                           delay=1 if job.attempt_count == 1 else 5)
        return True
    await jobs.finish(session, job, "failed", error_code=error_code,
                      error_message=error_message or error_code.replace("_", " "))
    if monitor is None:
        return True
    fingerprint = hashlib.sha256(f"{monitor.id}:{error_code}".encode()).hexdigest()
    if monitor.health_status != "failed" or monitor.failure_fingerprint != fingerprint:
        baseline = await session.get(Snapshot, monitor.baseline_snapshot_id) \
            if monitor.baseline_snapshot_id else None
        fields = baseline.extracted_data if baseline else {}
        await _event(session, monitor, job, "run_failed", before=fields or None,
            after=fields, summary=f"采集失败：{ERROR_SUMMARIES.get(error_code, error_code)}", fields=fields,
            fingerprint=fingerprint)
    monitor.health_status, monitor.failure_fingerprint = "failed", fingerprint
    monitor.last_failure_at = now
    await session.flush()
    return True


async def lease_expired(session: AsyncSession, job: Job) -> bool:
    """A lease that expired without a terminal write is one failed attempt."""
    job.lease_owner = job.lease_expires_at = None
    job.status = "running"
    return await fail_run(session, job, error_code="lease_expired",
                          error_message="Worker lease expired", retryable=True)
