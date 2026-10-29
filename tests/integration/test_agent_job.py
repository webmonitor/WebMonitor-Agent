"""An agent job fails cleanly without a model, keeping its drafts and history."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from webmonitor.agent.orchestration import _history, execute_job
from webmonitor.config import get_settings
from webmonitor.models import Conversation, Job, Message, User, utc_now
from webmonitor.services import jobs


async def running_agent_job(session) -> tuple[User, Job]:
    user = User(email=f"{uuid4().hex}@example.com", display_name="Agent",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    conversation = Conversation(user_id=user.id, title="agent")
    session.add(conversation)
    await session.flush()
    session.add(Message(conversation_id=conversation.id, user_id=user.id, role="user",
                        content="监控这个页面的价格"))
    job = Job(user_id=user.id, kind="agent", status="running",
              conversation_id=conversation.id, lease_owner="worker",
              lease_expires_at=utc_now() + timedelta(seconds=90), attempt_count=1,
              attempts=[{"number": 1, "status": "running", "started_at": utc_now().isoformat(),
                         "finished_at": None, "error_code": None, "retryable": False}])
    session.add(job)
    await session.flush()
    return user, job


@pytest.mark.asyncio
async def test_history_rebuilds_user_and_assistant_turns_in_order(session):
    user, job = await running_agent_job(session)
    session.add(Message(conversation_id=job.conversation_id, role="assistant",
                        content="请问是哪一种价格？"))
    await session.commit()

    history = await _history(job.conversation_id, 30)
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert history[0]["content"] == "监控这个页面的价格"
    assert await _history(job.conversation_id, 1) == [history[-1]]


@pytest.mark.asyncio
async def test_missing_model_fails_the_job_and_keeps_the_conversation(session):
    _, job = await running_agent_job(session)
    await session.commit()
    if get_settings().openai_api_key.get_secret_value():
        pytest.skip("A model is configured; this checks the unavailable-model path")

    await execute_job(job.id, "worker")
    await session.commit()

    stored = await session.get(Job, job.id, populate_existing=True)
    assert stored.status == "failed"
    assert stored.error_code == "model_unavailable"
    assert stored.finished_at is not None
    assert stored.lease_owner is None
    assert stored.attempts[-1]["status"] == "failed"
    assert stored.partial_text == ""
    messages = (await session.scalars(select(Message).where(
        Message.conversation_id == stored.conversation_id))).all()
    assert [message.role for message in messages] == ["user"]
    # The conversation stays usable: a new message can be queued again.
    assert await jobs.claim(session, kind="agent", worker_id="worker") is None
