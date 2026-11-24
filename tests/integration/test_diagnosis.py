"""Failure diagnosis reuses derived drafts and the ordinary agent job protocol."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests.integration import support
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Draft, Job, Message, utc_now
from webmonitor.security.auth import CurrentUser
from webmonitor.services import diagnosis, runs


async def failed_monitor(session):
    user, current, group = await support.seed_owner(session)
    _, draft, current = await support.prepare_draft(session, user, group)
    conversation = await session.get(Conversation, draft.conversation_id)
    monitor = await support.publish(session, conversation, draft, current)
    baseline_job = Job(user_id=user.id, kind="production", status="running",
        monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url,
        spec=monitor.spec, attempt_count=1, lease_owner="test",
        lease_expires_at=utc_now())
    session.add(baseline_job)
    await session.flush()
    assert await runs.commit_success(session, baseline_job, support.collection_result())
    failure = Job(user_id=user.id, kind="production", status="running",
        monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url,
        spec=monitor.spec, attempt_count=1, lease_owner="test",
        lease_expires_at=utc_now())
    session.add(failure)
    await session.flush()
    assert await runs.fail_run(session, failure, error_code="collection_invalid",
                               error_message="selector no longer matches")
    return user, current, monitor, failure


@pytest.mark.asyncio
async def test_diagnosis_clones_spec_injects_failure_and_queues_agent(session):
    _, current, monitor, failure = await failed_monitor(session)
    original_version = monitor.spec_version
    original_spec = monitor.spec

    conversation, draft = await diagnosis.diagnose_monitor(
        session, current, monitor.id, job_id=failure.id
    )

    assert draft.monitor_id == monitor.id
    assert draft.spec == original_spec
    assert draft.status == "draft"
    assert monitor.spec_version == original_version
    messages = (await session.scalars(select(Message).where(
        Message.conversation_id == conversation.id))).all()
    assert len(messages) == 1
    content = messages[0].content
    assert "collection_invalid" in content
    assert "selector no longer matches" in content
    assert str(monitor.baseline_snapshot_id) in content
    assert "original_monitor_spec" in content
    assert "untrusted_diagnostic_data" in content
    agent = await session.scalar(select(Job).where(
        Job.conversation_id == conversation.id, Job.kind == "agent"))
    assert agent is not None and agent.status == "queued"
    assert messages[0].job_id == agent.id
    assert (await session.scalars(select(Draft).where(
        Draft.conversation_id == conversation.id))).all() == [draft]


@pytest.mark.asyncio
async def test_diagnosis_enforces_owner_archived_and_failure_preconditions(session):
    user, current, monitor, failure = await failed_monitor(session)
    before = await session.scalar(select(func.count()).select_from(Conversation))
    with pytest.raises(DomainError) as raised:
        await diagnosis.diagnose_monitor(session, CurrentUser(uuid4(), role="member"), monitor.id)
    assert raised.value.code == "not_found"
    assert await session.scalar(select(func.count()).select_from(Conversation)) == before

    with pytest.raises(DomainError) as raised:
        await diagnosis.diagnose_monitor(session, current, monitor.id, job_id=uuid4())
    assert raised.value.code == "run_not_failed"

    monitor.archived_at = utc_now()
    with pytest.raises(DomainError) as raised:
        await diagnosis.diagnose_monitor(session, current, monitor.id, job_id=failure.id)
    assert raised.value.code == "monitor_archived"
    assert await session.scalar(select(func.count()).select_from(Conversation)) == before


@pytest.mark.asyncio
async def test_diagnosis_requires_a_failed_production_job(session):
    user, current, group = await support.seed_owner(session)
    _, draft, current = await support.prepare_draft(session, user, group)
    conversation = await session.get(Conversation, draft.conversation_id)
    monitor = await support.publish(session, conversation, draft, current)
    with pytest.raises(DomainError) as raised:
        await diagnosis.diagnose_monitor(session, current, monitor.id)
    assert raised.value.code == "run_not_failed"
