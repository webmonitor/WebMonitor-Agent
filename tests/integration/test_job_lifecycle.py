"""One claim protocol: leases, attempt history and retry requeue."""
from uuid import uuid4

import pytest

from webmonitor.models import Conversation, Draft, Job, User
from webmonitor.services import jobs


async def seed(session) -> User:
    user = User(email=f"{uuid4().hex}@example.com", display_name="Worker",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_claim_renew_and_finish(session):
    user = await seed(session)
    queued = await jobs.enqueue(session, user_id=user.id, kind="analyze", url="https://8.8.8.8/",
                                spec={"collection_mode": "http"})
    await session.commit()

    claimed = await jobs.claim(session, kind="analyze", worker_id="w1")
    await session.commit()
    assert claimed is not None and claimed.id == queued.id
    assert claimed.status == "running" and claimed.lease_owner == "w1"
    assert claimed.attempt_count == 1
    assert claimed.attempts[-1]["status"] == "running"

    assert await jobs.renew(session, claimed.id, "w2") is False
    assert await jobs.renew(session, claimed.id, "w1") is True
    await session.commit()

    await jobs.finish(session, claimed, "succeeded", result={"ok": True})
    await session.commit()
    stored = await session.get(Job, claimed.id)
    assert stored.status == "succeeded"
    assert stored.result == {"ok": True}
    assert stored.lease_owner is None
    assert stored.attempts[-1]["status"] == "succeeded"

    assert await jobs.claim(session, kind="analyze", worker_id="w1") is None


@pytest.mark.asyncio
async def test_expired_lease_is_reaped_and_requeued_with_history(session):
    user = await seed(session)
    job = await jobs.enqueue(session, user_id=user.id, kind="agent",
                             conversation_id=None)
    await session.commit()

    claimed = await jobs.claim(session, kind="agent", worker_id="w1")
    await session.commit()
    assert claimed is not None
    claimed.lease_expires_at = claimed.started_at
    await session.commit()

    # The first claim observes the expired lease and reaps it instead of running it.
    assert await jobs.claim(session, kind="agent", worker_id="w2") is None
    await session.commit()
    reaped = await session.get(Job, job.id)
    assert reaped.status == "queued"
    assert reaped.attempts[-1]["error_code"] == "lease_expired"
    assert reaped.attempts[-1]["retryable"] is True

    reclaimed = await jobs.claim(session, kind="agent", worker_id="w2")
    await session.commit()
    assert reclaimed is not None
    assert reclaimed.attempt_count == 2
    assert reclaimed.lease_owner == "w2"


@pytest.mark.asyncio
async def test_requeue_keeps_the_attempt_and_schedules_the_next_try(session):
    user = await seed(session)
    conversation = Conversation(user_id=user.id, title="Preview retry")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, revision=1)
    session.add(draft)
    await session.flush()
    await jobs.enqueue(session, user_id=user.id, kind="preview", draft_id=draft.id,
                       spec={"collection_mode": "http"})
    await session.commit()
    claimed = await jobs.claim(session, kind="preview", worker_id="w1")
    await session.commit()

    await jobs.requeue(session, claimed, error_code="target_unavailable", delay=5)
    await session.commit()
    stored = await session.get(Job, claimed.id)
    assert stored.status == "queued"
    assert stored.attempts[-1]["status"] == "failed"
    assert stored.attempts[-1]["retryable"] is True
    assert stored.available_at > stored.started_at

    assert await jobs.claim(session, kind="preview", worker_id="w1") is None


@pytest.mark.asyncio
async def test_cancel_stops_queued_work_immediately(session):
    user = await seed(session)
    job = await jobs.enqueue(session, user_id=user.id, kind="agent")
    await session.commit()

    await jobs.cancel(session, job)
    await session.commit()
    stored = await session.get(Job, job.id)
    assert stored.status == "cancelled"
    assert stored.error_code == "cancelled"
    assert await jobs.claim(session, kind="agent", worker_id="w1") is None


@pytest.mark.asyncio
async def test_wait_surfaces_job_failure(session):
    user = await seed(session)
    job = await jobs.enqueue(session, user_id=user.id, kind="analyze")
    await session.commit()
    await jobs.finish(session, job, "failed", error_code="target_unavailable")
    await session.commit()

    from webmonitor.errors import DomainError
    with pytest.raises(DomainError) as raised:
        await jobs.wait(job.id, timeout=1)
    assert raised.value.code == "target_unavailable"
