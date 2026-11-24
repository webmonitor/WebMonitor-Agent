"""A 304 completes the job without duplicating the trusted baseline."""
import pytest
from sqlalchemy import func, select

from tests.integration import support
from webmonitor.models import Event, Job, Snapshot, utc_now
from webmonitor.services import runs


@pytest.mark.asyncio
async def test_not_modified_preserves_baseline_and_recovers_health(session):
    user, current, group = await support.seed_owner(session)
    conversation, draft, current = await support.prepare_draft(session, user, group)
    monitor = await support.publish(session, conversation, draft, current)
    baseline_job = Job(user_id=user.id, kind="production", status="running",
        monitor_id=monitor.id, revision=1, url=monitor.url, spec=monitor.spec,
        attempt_count=1, lease_owner="test", lease_expires_at=utc_now())
    session.add(baseline_job)
    await session.flush()
    initial = {**support.collection_result(), "validator": {"etag": '"v1"'}}
    assert await runs.commit_success(session, baseline_job, initial)
    baseline_id = monitor.baseline_snapshot_id
    rule_state = monitor.rule_state
    assert monitor.collection_state["conditional"] == {"etag": '"v1"'}

    failed = Job(user_id=user.id, kind="production", status="running",
        monitor_id=monitor.id, revision=1, url=monitor.url, spec=monitor.spec,
        attempt_count=1, lease_owner="test", lease_expires_at=utc_now())
    session.add(failed)
    await session.flush()
    await runs.fail_run(session, failed, error_code="collection_failed")
    not_modified = Job(user_id=user.id, kind="production", status="running",
        monitor_id=monitor.id, revision=1, url=monitor.url, spec=monitor.spec,
        attempt_count=1, lease_owner="test", lease_expires_at=utc_now())
    session.add(not_modified)
    await session.flush()
    before = await session.scalar(select(func.count()).select_from(Snapshot))

    assert await runs.commit_not_modified(session, not_modified, {
        "final_url": monitor.url, "not_modified": True, "validator": {"etag": '"v1"'},
        "fields": {}, "coverage": {}, "evidence_refs": [], "warnings": [],
    })
    assert monitor.baseline_snapshot_id == baseline_id
    assert monitor.rule_state == rule_state
    assert monitor.health_status == "healthy"
    assert not_modified.status == "succeeded"
    assert not_modified.result["not_modified"] is True
    assert await session.scalar(select(func.count()).select_from(Snapshot)) == before
    recovered = await session.scalar(select(Event).where(
        Event.job_id == not_modified.id, Event.type == "recovered"))
    assert recovered is not None and recovered.snapshot_id == baseline_id
