"""Retention GC keeps history anchors and retries storage failures safely."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Delivery, Draft, Event, Job, Monitor, Snapshot, User, utc_now
from webmonitor.services import retention


@pytest.fixture(autouse=True)
def retention_settings(monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "30")
    monkeypatch.setenv("RETENTION_GC_BATCH_SIZE", "100")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def evidence(label: str, *, kind: str = "html") -> dict:
    return {"kind": kind, "bucket": "evidence", "object_key": f"test/{label}",
            "content_type": "text/html; charset=utf-8", "size_bytes": 10,
            "sha256": "0" * 64}


async def user_for(session) -> User:
    user = User(email=f"{uuid4().hex}@example.com", display_name="Retention",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    return user


async def monitor_for(session, user: User) -> Monitor:
    conversation = Conversation(user_id=user.id, title="Retention")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, status="published",
                  spec_revision=1, settings_revision=1)
    session.add(draft)
    await session.flush()
    monitor = Monitor(user_id=user.id, draft_id=draft.id, name="Retention", url="https://example.com",
        spec={}, spec_version=1, spec_hash="0" * 64, collection_mode="http",
        interval_seconds=3600, timezone="UTC", notification_group_ids=[],
        approved_recipients=[], baseline_status="pending_first_success", rule_state={},
        next_run_at=utc_now())
    session.add(monitor)
    await session.flush()
    return monitor


async def production_snapshot(session, monitor: Monitor, collected_at, ref: dict):
    job = Job(user_id=monitor.user_id, kind="production", status="succeeded",
        monitor_id=monitor.id, revision=1, created_at=collected_at, finished_at=collected_at,
        result={"evidence_refs": [ref]})
    session.add(job)
    await session.flush()
    snapshot = Snapshot(monitor_id=monitor.id, job_id=job.id, spec_version=1,
        final_url=monitor.url, extracted_data={}, coverage={}, rule_state={},
        evidence_refs=[ref], created_at=collected_at, collected_at=collected_at)
    session.add(snapshot)
    await session.flush()
    return job, snapshot


async def terminal_job(session, user: User, finished_at, ref: dict | None = None,
                       *, kind: str = "analyze", draft_id=None) -> Job:
    job = Job(user_id=user.id, kind=kind, status="succeeded", draft_id=draft_id,
        revision=1 if draft_id is not None else None, created_at=finished_at,
        finished_at=finished_at,
        result={"evidence_refs": [ref]} if ref is not None else {"ok": True})
    session.add(job)
    await session.flush()
    return job


def delivery_for(monitor: Monitor, event: Event, created_at, status: str) -> Delivery:
    terminal_at = {
        "sent": {"sent_at": created_at},
        "failed": {"failed_at": created_at},
        "cancelled": {"cancelled_at": created_at},
    }.get(status, {})
    return Delivery(user_id=monitor.user_id, monitor_id=monitor.id, event_id=event.id,
        channel="email", recipient=f"{status}@example.com", subject="Retention",
        body_text="Retention", payload={}, status=status, created_at=created_at,
        available_at=created_at, **terminal_at)


@pytest.mark.asyncio
async def test_baseline_and_event_snapshots_are_exempt(session, monkeypatch):
    user = await user_for(session)
    monitor = await monitor_for(session, user)
    old = utc_now() - timedelta(days=60)
    baseline_job, baseline = await production_snapshot(session, monitor, old, evidence("baseline"))
    monitor.baseline_snapshot_id = baseline.id
    event_job, evented = await production_snapshot(session, monitor, old, evidence("event"))
    session.add(Event(monitor_id=monitor.id, job_id=event_job.id, snapshot_id=evented.id,
                      type="content_changed", created_at=utc_now()))
    ordinary_job, ordinary = await production_snapshot(session, monitor, old, evidence("ordinary"))
    recent_job, recent = await production_snapshot(session, monitor, utc_now(), evidence("recent"))
    await session.commit()

    deleted = []

    async def remove(bucket, key):
        assert not session.in_transaction()
        deleted.append((bucket, key))

    monkeypatch.setattr(retention, "delete_evidence", remove)
    stats = await retention.collect(session)

    assert deleted == [("evidence", "test/ordinary")]
    assert stats.snapshots_deleted == 1 and stats.jobs_deleted == 1
    assert stats.evidence_deleted == 1 and stats.failures == 0
    snapshot_ids = set(await session.scalars(select(Snapshot.id)))
    job_ids = set(await session.scalars(select(Job.id)))
    assert snapshot_ids == {baseline.id, evented.id, recent.id}
    assert ordinary.id not in snapshot_ids
    assert job_ids == {baseline_job.id, event_job.id, recent_job.id}
    assert ordinary_job.id not in job_ids


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["sent", "failed", "cancelled"])
async def test_terminal_delivery_and_delivery_free_event_release_snapshot(
        session, monkeypatch, status):
    user = await user_for(session)
    monitor = await monitor_for(session, user)
    old = utc_now() - timedelta(days=60)
    ref = evidence(f"terminal-{status}")
    job, snapshot = await production_snapshot(session, monitor, old, ref)
    event = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                  type="content_changed", created_at=old)
    session.add(event)
    await session.flush()
    delivery = delivery_for(monitor, event, old, status)
    session.add(delivery)
    await session.commit()
    deleted = []

    async def remove(bucket, key):
        deleted.append((bucket, key))

    monkeypatch.setattr(retention, "delete_evidence", remove)
    stats = await retention.collect(session)

    assert stats.deliveries_deleted == 1 and stats.events_deleted == 1
    assert stats.snapshots_deleted == 1 and stats.jobs_deleted == 1
    assert stats.evidence_deleted == 1 and stats.failures == 0
    assert deleted == [("evidence", ref["object_key"])]
    assert await session.get(Delivery, delivery.id) is None
    assert await session.get(Event, event.id) is None
    assert await session.get(Snapshot, snapshot.id) is None
    assert await session.get(Job, job.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "sending", "retrying"])
async def test_active_delivery_preserves_event_snapshot_and_evidence(
        session, monkeypatch, status):
    user = await user_for(session)
    monitor = await monitor_for(session, user)
    old = utc_now() - timedelta(days=60)
    ref = evidence(f"active-{status}")
    job, snapshot = await production_snapshot(session, monitor, old, ref)
    event = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                  type="content_changed", created_at=old)
    session.add(event)
    await session.flush()
    delivery = delivery_for(monitor, event, old, status)
    session.add(delivery)
    await session.commit()

    async def unexpected_delete(bucket, key):
        raise AssertionError("an active delivery must preserve its evidence")

    monkeypatch.setattr(retention, "delete_evidence", unexpected_delete)
    stats = await retention.collect(session)

    assert stats == retention.RetentionStats()
    assert await session.get(Delivery, delivery.id) is not None
    assert await session.get(Event, event.id) is not None
    assert await session.get(Snapshot, snapshot.id) is not None
    assert await session.get(Job, job.id) is not None


@pytest.mark.asyncio
async def test_all_gc_phases_share_one_batch_budget(session, monkeypatch):
    monkeypatch.setenv("RETENTION_GC_BATCH_SIZE", "1")
    get_settings.cache_clear()
    user = await user_for(session)
    monitor = await monitor_for(session, user)
    old = utc_now() - timedelta(days=60)
    ref = evidence("shared-budget")
    job, snapshot = await production_snapshot(session, monitor, old, ref)
    event = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                  type="content_changed", created_at=old)
    session.add(event)
    await session.flush()
    delivery = delivery_for(monitor, event, old, "sent")
    session.add(delivery)
    await session.commit()
    deleted = []

    async def remove(bucket, key):
        deleted.append((bucket, key))

    monkeypatch.setattr(retention, "delete_evidence", remove)
    first = await retention.collect(session)
    assert (first.deliveries_deleted, first.events_deleted,
            first.snapshots_deleted, first.jobs_deleted) == (1, 0, 0, 0)
    assert await session.get(Event, event.id) is not None
    await session.rollback()

    second = await retention.collect(session)
    assert (second.deliveries_deleted, second.events_deleted,
            second.snapshots_deleted, second.jobs_deleted) == (0, 1, 0, 0)
    assert await session.get(Snapshot, snapshot.id) is not None
    assert deleted == []
    await session.rollback()

    third = await retention.collect(session)
    assert (third.deliveries_deleted, third.events_deleted,
            third.snapshots_deleted, third.jobs_deleted) == (0, 0, 1, 1)
    assert deleted == [("evidence", ref["object_key"])]


@pytest.mark.asyncio
async def test_s3_failure_retains_job_and_succeeds_on_retry(session, monkeypatch):
    user = await user_for(session)
    old = utc_now() - timedelta(days=60)
    ref = evidence("retry")
    job = await terminal_job(session, user, old, ref)
    await session.commit()
    calls = []

    async def remove(bucket, key):
        assert not session.in_transaction()
        calls.append((bucket, key))
        if len(calls) == 1:
            raise DomainError("storage_unavailable", 503)

    monkeypatch.setattr(retention, "delete_evidence", remove)
    first = await retention.collect(session)

    assert first.failures == 1 and first.jobs_deleted == 0
    assert await session.get(Job, job.id) is not None
    assert (await session.get(Job, job.id)).result["evidence_refs"] == [ref]

    second = await retention.collect(session)
    assert second.failures == 0 and second.jobs_deleted == 1
    assert calls == [("evidence", "test/retry")] * 2
    assert await session.get(Job, job.id) is None


@pytest.mark.asyncio
async def test_current_draft_reference_defers_job_and_evidence_gc(session, monkeypatch):
    user = await user_for(session)
    conversation = Conversation(user_id=user.id, title="Preview retention")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, spec_revision=1,
                  extraction_preview={"evidence_refs": [evidence("draft")]})
    session.add(draft)
    await session.flush()
    old = utc_now() - timedelta(days=60)
    job = await terminal_job(session, user, old, evidence("draft"), kind="preview",
                             draft_id=draft.id)
    await session.commit()
    deleted = []

    async def remove(bucket, key):
        deleted.append((bucket, key))

    monkeypatch.setattr(retention, "delete_evidence", remove)
    first = await retention.collect(session)
    assert first.jobs_deleted == 0 and deleted == []
    assert await session.get(Job, job.id) is not None

    draft.extraction_preview = {"evidence_refs": []}
    await session.commit()
    second = await retention.collect(session)
    assert second.jobs_deleted == 1
    assert deleted == [("evidence", "test/draft")]
    assert await session.get(Job, job.id) is None


@pytest.mark.asyncio
async def test_zero_retention_disables_gc(session, monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "0")
    get_settings.cache_clear()
    user = await user_for(session)
    job = await terminal_job(session, user, utc_now() - timedelta(days=3650), evidence("disabled"))
    await session.commit()

    async def unexpected_delete(bucket, key):
        raise AssertionError("disabled GC must not touch S3")

    monkeypatch.setattr(retention, "delete_evidence", unexpected_delete)
    stats = await retention.collect(session)
    assert stats == retention.RetentionStats()
    assert await session.get(Job, job.id) is not None


@pytest.mark.asyncio
async def test_each_pass_is_bounded(session, monkeypatch):
    monkeypatch.setenv("RETENTION_GC_BATCH_SIZE", "2")
    get_settings.cache_clear()
    user = await user_for(session)
    old = utc_now() - timedelta(days=60)
    for index in range(3):
        await terminal_job(session, user, old + timedelta(seconds=index))
    await session.commit()

    first = await retention.collect(session)
    assert first.jobs_deleted == 2
    assert await session.scalar(select(func.count()).select_from(Job)) == 1
    await session.rollback()
    second = await retention.collect(session)
    assert second.jobs_deleted == 1
    assert await session.scalar(select(func.count()).select_from(Job)) == 0
