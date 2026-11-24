"""First success only establishes a baseline; later runs publish events and delivery."""
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from webmonitor.models import (
    Delivery,
    Draft,
    Event,
    Job,
    Monitor,
    NotificationGroup,
    Snapshot,
    User,
    utc_now,
)
from webmonitor.schemas.monitors import MonitorSpec, content_hash
from webmonitor.services import notifications, runs


def spec_for() -> MonitorSpec:
    return MonitorSpec.model_validate({
        "name": "Heading watch",
        "url": "https://8.8.8.8/",
        "collection_mode": "http",
        "fields": [{"name": "title", "type": "text", "semantic": "Heading", "selector": "h1"}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "text_changed", "field": "title"}]},
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
    draft = Draft(user_id=user.id, conversation_id=conversation.id, status="published",
                  spec_revision=1, settings_revision=1)
    session.add(draft)
    await session.flush()
    spec = spec_for()
    monitor = Monitor(user_id=user.id, draft_id=draft.id, name=spec.name, url=spec.url,
        status="active", spec=spec.model_dump(mode="json"), spec_version=1,
        spec_hash=content_hash(spec), collection_mode="http", interval_seconds=60,
        timezone="UTC", notification_group_ids=[str(group.id)],
        approved_recipients=[{"email": "ops@example.com", "group_ids": [str(group.id)]}],
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


async def queue_event_at(session, monitor: Monitor, created_at: datetime) -> Event:
    job = await running_job(session, monitor)
    job.status, job.finished_at = "succeeded", created_at
    event = Event(monitor_id=monitor.id, job_id=job.id, type="content_changed",
                  change={"before": {"title": "A"}, "after": {"title": "B"},
                          "summary": "title changed", "differences": []},
                  created_at=created_at)
    session.add(event)
    await session.flush()
    await notifications.enqueue_event_deliveries(session, monitor, event, {"title": "B"})
    return event


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
    assert await session.scalar(select(func.count()).select_from(Delivery)) == 0


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
    deliveries = (await session.scalars(select(Delivery))).all()
    assert len(deliveries) == 1
    assert deliveries[0].recipient == "ops@example.com"
    assert deliveries[0].status == "queued"
    assert deliveries[0].message_id.startswith("<")
    body = deliveries[0].body_text
    assert "之前：A" in body
    assert "之后：B" in body
    assert '"B"' not in body

    # An unchanged value must stay silent.
    await runs.commit_success(session, await running_job(session, monitor), result("B"))
    await session.commit()
    assert await session.scalar(select(func.count()).select_from(Event)) == 1


@pytest.mark.asyncio
async def test_consecutive_hits_hold_the_baseline_until_the_same_value_confirms(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    monitor.spec = {**monitor.spec, "change_rules": {
        **monitor.spec["change_rules"], "consecutive_hits": 2}}
    await runs.commit_success(session, await running_job(session, monitor), result("A"))
    await session.commit()
    baseline_id = monitor.baseline_snapshot_id

    await runs.commit_success(session, await running_job(session, monitor), result("B"))
    await session.commit()
    assert monitor.baseline_snapshot_id == baseline_id
    assert monitor.rule_state["confirmation"]["count"] == 1
    assert await session.scalar(select(func.count()).select_from(Event)) == 0

    await runs.commit_success(session, await running_job(session, monitor), result("B"))
    await session.commit()
    assert monitor.baseline_snapshot_id != baseline_id
    assert "confirmation" not in monitor.rule_state
    event = await session.scalar(select(Event))
    assert event.change["before"] == {"title": "A"}
    assert event.change["after"] == {"title": "B"}
    assert await session.scalar(select(func.count()).select_from(Event)) == 1
    assert await session.scalar(select(func.count()).select_from(Delivery)) == 1

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


@pytest.mark.asyncio
async def test_webhook_channel_queues_one_json_delivery_and_revokes_on_change(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    monitor.delivery_channel = "webhook"
    monitor.webhook_url = "https://hooks.example.com/ops"
    monitor.approved_recipients = []
    await session.flush()
    await runs.commit_success(session, await running_job(session, monitor), result("A"))
    await session.commit()

    await runs.commit_success(session, await running_job(session, monitor), result("B"))
    await session.commit()

    deliveries = (await session.scalars(select(Delivery))).all()
    assert len(deliveries) == 1
    delivery = deliveries[0]
    assert delivery.channel == "webhook"
    assert delivery.recipient == "https://hooks.example.com/ops"
    assert delivery.html == ""
    body = json.loads(delivery.body_text)
    assert body["monitor"]["id"] == str(monitor.id)
    assert body["event"]["type"] == "content_changed"
    assert body["change"]["before"] == {"title": "A"}
    assert body["change"]["after"] == {"title": "B"}
    assert await notifications.authorized(session, delivery)

    monitor.webhook_url = "https://hooks.example.com/replacement"
    await session.flush()
    assert not await notifications.authorized(session, delivery)

    monitor.webhook_url = delivery.recipient
    monitor.delivery_channel = "email"
    await session.flush()
    assert not await notifications.authorized(session, delivery)


@pytest.mark.asyncio
async def test_cooldown_chains_from_the_latest_queued_delivery(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    monitor.notification_cooldown_seconds = 3600
    base = datetime(2026, 7, 1, 12, tzinfo=UTC)

    first = await queue_event_at(session, monitor, base)
    second = await queue_event_at(session, monitor, base + timedelta(minutes=5))
    third = await queue_event_at(session, monitor, base + timedelta(minutes=10))
    await session.commit()

    deliveries = (await session.scalars(select(Delivery).order_by(Delivery.available_at))).all()
    assert [row.available_at for row in deliveries] == [
        base, base + timedelta(hours=1), base + timedelta(hours=2)]
    assert {row.event_id for row in deliveries} == {first.id, second.id, third.id}
    assert await session.scalar(select(func.count()).select_from(Event)) == 3
    assert all(row.status == "queued" for row in deliveries)


@pytest.mark.asyncio
async def test_cross_midnight_quiet_hours_use_monitor_dst_zone_for_every_recipient(session):
    user, group = await seed(session)
    group.members = [{"email": "ops@example.com", "active": True},
                     {"email": "dev@example.com", "active": True}]
    monitor = await make_monitor(session, user, group)
    monitor.approved_recipients = [
        {"email": "ops@example.com", "group_ids": [str(group.id)]},
        {"email": "dev@example.com", "group_ids": [str(group.id)]},
    ]
    monitor.timezone = "America/New_York"
    monitor.quiet_hours = {"start": "22:00", "end": "07:00"}
    # July 1 at 22:00 EDT: the next 07:00 is July 2 at 11:00 UTC.
    detected_at = datetime(2026, 7, 2, 2, tzinfo=UTC)
    event = await queue_event_at(session, monitor, detected_at)
    await session.commit()

    stored_event = await session.get(Event, event.id)
    assert stored_event is not None
    deliveries = (await session.scalars(select(Delivery).where(
        Delivery.event_id == event.id))).all()
    assert len(deliveries) == 2
    assert {row.recipient for row in deliveries} == {"ops@example.com", "dev@example.com"}
    assert {row.available_at for row in deliveries} == {datetime(2026, 7, 2, 11, tzinfo=UTC)}
    assert all(row.status == "queued" for row in deliveries)


@pytest.mark.asyncio
async def test_quiet_hours_never_move_a_repeated_dst_time_into_the_past(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    monitor.timezone = "America/New_York"
    monitor.quiet_hours = {"start": "22:00", "end": "01:30"}
    first = await queue_event_at(session, monitor, datetime(2026, 11, 1, 5, tzinfo=UTC))
    second = await queue_event_at(session, monitor, datetime(2026, 11, 1, 6, tzinfo=UTC))
    await session.commit()

    first_delivery = await session.scalar(select(Delivery).where(Delivery.event_id == first.id))
    second_delivery = await session.scalar(select(Delivery).where(Delivery.event_id == second.id))
    assert first_delivery.available_at == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert second_delivery.available_at == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
