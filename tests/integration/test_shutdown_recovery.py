"""Process interruption remains recoverable and never impersonates user cancellation."""
import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest

from webmonitor.agent import orchestration
from webmonitor.collection.types import CollectionResult
from webmonitor.db import get_session_factory
from webmonitor.models import Conversation, Job, Message, User, utc_now
from webmonitor.services import jobs
from webmonitor import worker


async def analyzed_job(session):
    user = User(email=f"{uuid4().hex}@example.com", display_name="Worker",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    await jobs.enqueue(session, user_id=user.id, kind="analyze",
        url="https://8.8.8.8/", spec={"collection_mode": "http"})
    await session.commit()
    claimed = await jobs.claim(session, kind="analyze", worker_id="worker")
    await session.commit()
    assert claimed is not None
    return claimed


@pytest.mark.asyncio
@pytest.mark.parametrize("user_cancelled,expected", [
    (False, "queued"),
    (True, "cancelled"),
])
async def test_collection_interruption_uses_only_the_db_cancellation_marker(
        session, monkeypatch, user_cancelled, expected):
    claimed = await analyzed_job(session)

    async def interrupted(*args, **kwargs):
        if user_cancelled:
            # The cancellation arrives after collection started, not at the
            # initial preflight check where no CancelledError would be raised.
            async with get_session_factory()() as active:
                live = await active.get(Job, claimed.id, populate_existing=True)
                live.cancel_requested_at = utc_now()
                await active.commit()
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "collect_http", interrupted)
    with pytest.raises(asyncio.CancelledError):
        await worker._collect(claimed.id, "worker")

    stored = await session.get(Job, claimed.id, populate_existing=True)
    assert stored.status == expected
    if user_cancelled:
        assert stored.error_code == "collection_cancelled"
    else:
        assert stored.error_code == "worker_interrupted"
        assert stored.attempts[-1]["retryable"] is True


@pytest.mark.asyncio
async def test_agent_shutdown_requeues_instead_of_cancelling(session, monkeypatch):
    user = User(email=f"{uuid4().hex}@example.com", display_name="Agent",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    conversation = Conversation(user_id=user.id, title="Shutdown")
    session.add(conversation)
    await session.flush()
    session.add(Message(conversation_id=conversation.id, user_id=user.id,
                        role="user", content="watch this page"))
    job = Job(user_id=user.id, kind="agent", status="running",
        conversation_id=conversation.id, lease_owner="worker",
        lease_expires_at=utc_now() + timedelta(seconds=90), attempt_count=1,
        attempts=[{"number": 1, "status": "running", "started_at": utc_now().isoformat(),
                   "finished_at": None, "error_code": None, "retryable": False}],
        partial_text="uncommitted display text")
    session.add(job)
    await session.commit()

    async def interrupted(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(orchestration, "_context", interrupted)
    with pytest.raises(asyncio.CancelledError):
        await orchestration.execute_job(job.id, "worker")

    stored = await session.get(Job, job.id, populate_existing=True)
    assert stored.status == "queued"
    assert stored.cancel_requested_at is None
    assert stored.error_code == "worker_interrupted"
    assert stored.partial_text == ""
    assert stored.attempts[-1]["retryable"] is True


@pytest.mark.asyncio
async def test_waiting_child_is_not_cancelled_during_worker_shutdown(session):
    claimed = await analyzed_job(session)
    jobs.begin_worker_shutdown()
    waiting = asyncio.create_task(jobs.wait(
        claimed.id, timeout=60, cancel_on_timeout=True))
    try:
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
    finally:
        await asyncio.gather(waiting, return_exceptions=True)
        jobs.reset_worker_shutdown()

    stored = await session.get(Job, claimed.id, populate_existing=True)
    assert stored.status == "running"
    assert stored.cancel_requested_at is None
    assert stored.error_code is None


@pytest.mark.asyncio
async def test_cancellation_after_commit_does_not_delete_referenced_evidence(
        session, monkeypatch):
    claimed = await analyzed_job(session)
    reference = {"kind": "html", "bucket": "evidence", "object_key": "analysis/committed",
                 "content_type": "text/html; charset=utf-8", "size_bytes": 5,
                 "sha256": "a" * 64}
    deleted = []

    async def collected(*args, **kwargs):
        return CollectionResult("https://8.8.8.8/", "<html>", b"png", {},
                                {"scope": "full", "description": "test"}, 1)

    async def upload(*, prefix, kind, data):
        if kind != "screenshot":
            return reference
        # Simulate cancellation arriving just after the result transaction has
        # committed. The first uploaded object is now referenced by the job.
        async with get_session_factory()() as active, active.begin():
            live = await worker._locked(active, claimed.id)
            await jobs.finish(active, live, "succeeded",
                              result={"evidence_refs": [reference]})
        raise asyncio.CancelledError

    async def delete(bucket, key):
        deleted.append((bucket, key))

    monkeypatch.setattr(worker, "collect_http", collected)
    monkeypatch.setattr(worker, "upload_evidence", upload)
    monkeypatch.setattr(worker, "delete_evidence", delete)
    with pytest.raises(asyncio.CancelledError):
        await worker._collect(claimed.id, "worker")

    stored = await session.get(Job, claimed.id, populate_existing=True)
    assert stored.status == "succeeded"
    assert stored.result["evidence_refs"] == [reference]
    assert deleted == []
