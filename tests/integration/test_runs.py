"""First success only establishes a baseline; later runs publish events and mail."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from webmonitor.models import (
    Draft,
    EmailDelivery,
    Event,
    Job,
    Monitor,
    NotificationGroup,
    Snapshot,
    User,
    utc_now,
)
from webmonitor.schemas.monitors import DraftSpec, content_hash
from webmonitor.services import runs


def spec_for(group_id) -> DraftSpec:
    return DraftSpec.model_validate({
        "name": "Heading watch",
        "url": "https://8.8.8.8/",
        "collection_mode": "http",
        "fields": [{"name": "title", "type": "text", "semantic": "Heading", "selector": "h1"}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "text_changed", "field": "title"}]},
        "schedule": {"interval_seconds": 60, "timezone": "UTC"},
        "notification_group_ids": [str(group_id)],
        "coverage": {"scope": "full", "description": "Single heading"},
    })


async def seed(session):
    user = User(email=f"{uuid4().hex}@example.com", display_name="Owner",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    group = NotificationGroup(name=f"Ops {uuid4().hex}", created_by_user_id=user.id,
        members=[{"email": "ops@example.com", "active": True}])
    session.add(group)
    await session.flush()
    return user, group


async def make_monitor(session, user, group) -> Monitor:
    from webmonitor.models import Conversation
    conversation = Conversation(user_id=user.id, title="runs")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, revision=1, status="published")
    session.add(draft)
    await session.flush()
    spec = spec_for(group.id)
    monitor = Monitor(user_id=user.id, draft_id=draft.id, name=spec.name, url=spec.url,
        status="active", spec=spec.model_dump(mode="json"), spec_version=1,
        spec_hash=content_hash(spec), collection_mode="http", interval_seconds=60,
        timezone="UTC", notification_group_ids=[str(group.id)],
        baseline_status="pending_first_success", rule_state={}, next_run_at=utc_now())
    session.add(monitor)
    await session.flush()
    return monitor


async def running_job(session, monitor, *, attempt=1) -> Job:
    # A monitor may hold at most one active production job.
    for active in (await session.scalars(select(Job).where(Job.monitor_id == monitor.id,
            Job.kind == "production", Job.status.in_(("queued", "running"))))).all():
        active.status, active.finished_at = "cancelled", utc_now()
        active.lease_owner = active.lease_expires_at = None
    await session.flush()
    job = Job(user_id=monitor.user_id, kind="production", status="running",
        monitor_id=monitor.id, url=monitor.url, spec=monitor.spec, revision=monitor.spec_version,
        attempt_count=attempt, attempts=[{"number": attempt, "status": "running",
            "started_at": utc_now().isoformat(), "finished_at": None,
            "error_code": None, "retryable": False}],
        lease_owner="worker", lease_expires_at=utc_now() + timedelta(seconds=90))
    session.add(job)
    await session.flush()
    return job


def result(title: str) -> dict:
    return {"final_url": "https://8.8.8.8/", "fields": {"title": title},
            "coverage": {"scope": "full", "description": "Single heading"},
            "evidence_refs": [], "warnings": [], "duration_ms": 5}


@pytest.mark.asyncio
async def test_first_success_establishes_the_baseline_without_events(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    job = await running_job(session, monitor)

    assert await runs.commit_success(session, job, result("A")) is True
    await session.commit()

    stored = await session.get(Monitor, monitor.id)
    assert stored.baseline_status == "ready"
    assert stored.health_status == "healthy"
    assert stored.baseline_snapshot_id is not None
    snapshot = await session.get(Snapshot, stored.baseline_snapshot_id)
    assert snapshot.job_id == job.id
    assert snapshot.extracted_data == {"title": "A"}
    assert await session.scalar(select(func.count()).select_from(Event)) == 0
    assert await session.scalar(select(func.count()).select_from(EmailDelivery)) == 0


@pytest.mark.asyncio
async def test_changed_value_publishes_one_event_and_one_delivery(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    await runs.commit_success(session, await running_job(session, monitor), result("A"))
    await session.commit()

    job = await running_job(session, monitor)
    await runs.commit_success(session, job, result("B"))
    await session.commit()

    events = (await session.scalars(select(Event))).all()
    assert len(events) == 1
    assert events[0].type == "content_changed"
    assert events[0].change["before"] == {"title": "A"}
    assert events[0].change["after"] == {"title": "B"}
    deliveries = (await session.scalars(select(EmailDelivery))).all()
    assert len(deliveries) == 1
    assert deliveries[0].recipient == "ops@example.com"
    assert deliveries[0].status == "queued"
    assert deliveries[0].message_id.startswith("<")
    assert '"B"' in deliveries[0].body_text

    # An unchanged value must stay silent.
    await runs.commit_success(session, await running_job(session, monitor), result("B"))
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(Event)) == 1


@pytest.mark.asyncio
async def test_retryable_failure_requeues_until_attempts_are_exhausted(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    await runs.commit_success(session, await running_job(session, monitor), result("A"))
    await session.commit()

    job = await running_job(session, monitor)
    assert await runs.fail_run(session, job, error_code="target_unavailable",
                               retryable=True) is True
    await session.commit()
    retried = await session.get(Job, job.id)
    assert retried.status == "queued"
    assert retried.attempts[-1]["retryable"] is True
    assert await session.scalar(select(func.count()).select_from(Event)) == 0

    exhausted = await running_job(session, monitor, attempt=3)
    await runs.fail_run(session, exhausted, error_code="target_unavailable", retryable=True)
    await session.commit()
    stored = await session.get(Monitor, monitor.id)
    assert stored.health_status == "failed"
    assert stored.last_failure_at is not None
    assert stored.baseline_snapshot_id is not None
    events = (await session.scalars(select(Event))).all()
    assert [event.type for event in events] == ["run_failed"]

    # The same failure fingerprint is only reported once.
    repeated = await running_job(session, monitor, attempt=3)
    await runs.fail_run(session, repeated, error_code="target_unavailable", retryable=True)
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(Event)) == 1

    # Recovering with the same value reports recovery only; a change would also fire.
    recovered = await running_job(session, monitor)
    await runs.commit_success(session, recovered, result("A"))
    await session.commit()
    types = [event.type for event in (await session.scalars(
        select(Event).order_by(Event.created_at))).all()]
    assert types == ["run_failed", "recovered"]
    assert (await session.get(Monitor, monitor.id)).health_status == "healthy"


@pytest.mark.asyncio
async def test_schedule_due_enqueues_one_job_and_advances_the_clock(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    scheduled_before = monitor.next_run_at

    assert await runs.schedule_due(session) == 1
    await session.commit()
    jobs = (await session.scalars(select(Job))).all()
    assert len(jobs) == 1
    assert jobs[0].kind == "production" and jobs[0].revision == monitor.spec_version
    advanced = await session.get(Monitor, monitor.id)
    assert advanced.next_run_at > scheduled_before

    # A monitor with queued work is not scheduled twice.
    assert await runs.schedule_due(session, now=advanced.next_run_at) == 0
