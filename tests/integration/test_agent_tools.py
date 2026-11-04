"""Tool boundaries: the run budget, child-job cancellation and the hourly cap."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from agents.tool_context import ToolContext
from sqlalchemy import select

from webmonitor.agent.runtime import RuntimeContext
from webmonitor.agent.tools import analyze_target, save_monitor_draft
from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Draft, Job, User, utc_now
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.security.auth import CurrentUser
from webmonitor.services import conversations, jobs


def build_spec() -> MonitorSpec:
    return MonitorSpec.model_validate({
        "name": "Notice watch",
        "url": "https://8.8.8.8/notice",
        "collection_mode": "http",
        "fields": [{"name": "page_title", "type": "text", "semantic": "Page title",
                    "selector": "h1"}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "text_changed", "field": "page_title"}]},
        "coverage": {"scope": "full", "description": "Page title"},
    })


async def running_agent_job(session) -> tuple[User, Job]:
    user = User(email=f"{uuid4().hex}@example.com", display_name="Agent",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    conversation = Conversation(user_id=user.id, title="agent")
    session.add(conversation)
    await session.flush()
    job = Job(user_id=user.id, kind="agent", status="running",
              conversation_id=conversation.id, lease_owner="worker",
              lease_expires_at=utc_now() + timedelta(seconds=90), attempt_count=1)
    session.add(job)
    await session.flush()
    return user, job


def _runtime(user: User, job: Job) -> RuntimeContext:
    return RuntimeContext(user=CurrentUser(user_id=user.id, role=user.role),
                          conversation_id=job.conversation_id, job_id=job.id,
                          worker_id="worker")


async def _steps(session, job_id) -> list[dict]:
    stored = await session.scalar(select(Job).where(Job.id == job_id)
                                  .execution_options(populate_existing=True))
    return list(stored.steps or [])


@pytest.mark.asyncio
async def test_wait_timeout_cancels_the_job(session):
    user, _ = await running_agent_job(session)
    job = await jobs.enqueue(session, user_id=user.id, kind="analyze",
                             url="https://8.8.8.8/page", spec={"collection_mode": "http"})
    await session.commit()
    with pytest.raises(DomainError) as raised:
        await jobs.wait(job.id, timeout=0.01, cancel_on_timeout=True)
    assert raised.value.code == "job_timeout"
    stored = await session.scalar(select(Job).where(Job.id == job.id)
                                  .with_for_update()
                                  .execution_options(populate_existing=True))
    assert stored.status == "cancelled"
    await session.commit()


@pytest.mark.asyncio
async def test_browser_analysis_requires_http_evidence(session):
    user, job = await running_agent_job(session)
    await session.commit()
    arguments = json.dumps({"url": "https://8.8.8.8/page", "collection_mode": "browser"})
    context = ToolContext(context=_runtime(user, job), tool_name="analyze_target",
                          tool_call_id="call-1", tool_arguments=arguments)
    response = await analyze_target.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert response["error"]["code"] == "http_analysis_required"
    steps = await _steps(session, job.id)
    assert (steps[-1]["status"], steps[-1]["error_code"]) == ("failed",
                                                              "http_analysis_required")
    assert isinstance(steps[-1]["duration_ms"], int)


@pytest.mark.asyncio
async def test_stale_draft_revision_is_rejected(session):
    user, job = await running_agent_job(session)
    await session.commit()
    runtime = _runtime(user, job)
    runtime.draft_id = uuid4()
    runtime.spec_revision = 1
    arguments = json.dumps({"spec": build_spec().model_dump(mode="json")})
    context = ToolContext(context=runtime, tool_name="save_monitor_draft",
                          tool_call_id="call-1", tool_arguments=arguments)
    response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert response["error"]["code"] == "stale_revision"
    assert (await session.scalars(select(Draft))).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("forbidden", [
    {"schedule": {"interval_seconds": 60, "timezone": "UTC"}},
    {"notification_group_ids": ["00000000-0000-4000-8000-000000000001"]},
    {"email_template_id": "00000000-0000-4000-8000-000000000002"},
])
async def test_agent_spec_cannot_write_delivery_settings(session, forbidden):
    """The agent owns the collection definition only; settings are user-owned."""
    user, job = await running_agent_job(session)
    await session.commit()
    runtime = _runtime(user, job)
    arguments = json.dumps({"spec": {**build_spec().model_dump(mode="json"), **forbidden}})
    context = ToolContext(context=runtime, tool_name="save_monitor_draft",
                          tool_call_id="call-1", tool_arguments=arguments)
    response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert response["error"]["code"] == "invalid_tool_input"
    assert (await session.scalars(select(Draft))).all() == []


@pytest.mark.asyncio
async def test_exhausted_budget_refuses_before_enqueuing(session):
    user, job = await running_agent_job(session)
    await session.commit()
    runtime = _runtime(user, job)
    runtime.deadline = 0.0
    arguments = json.dumps({"url": "https://8.8.8.8/page"})
    context = ToolContext(context=runtime, tool_name="analyze_target",
                          tool_call_id="call-1", tool_arguments=arguments)
    response = await analyze_target.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert response["error"]["code"] == "run_budget_exhausted"
    stored = await session.scalars(select(Job).where(Job.kind == "analyze")
                                   .execution_options(populate_existing=True))
    assert stored.all() == []


@pytest.mark.asyncio
async def test_hourly_run_cap_blocks_a_new_message(session, monkeypatch):
    user, job = await running_agent_job(session)
    previous = await session.scalar(select(Job).where(Job.id == job.id))
    await jobs.finish(session, previous, "succeeded")
    await session.commit()
    monkeypatch.setenv("AGENT_RUNS_PER_HOUR", "1")
    get_settings.cache_clear()
    try:
        with pytest.raises(DomainError) as raised:
            await conversations.post_message(
                session, CurrentUser(user_id=user.id, role=user.role), job.conversation_id,
                content="再监控一个页面", client_message_id="cap-1")
    finally:
        get_settings.cache_clear()
    assert raised.value.code == "rate_limited"
    assert raised.value.details["limit"] == 1
    assert raised.value.details["retry_after"] >= 1


@pytest.mark.asyncio
async def test_preview_tool_returns_the_evidence_the_model_must_describe(session, monkeypatch):
    from support import build_spec, collect, collection_result
    from webmonitor.agent.tools import preview_monitor
    from webmonitor.services import drafts

    user, job = await running_agent_job(session)
    runtime = _runtime(user, job)
    draft = await drafts.save_spec(session, runtime.user, conversation_id=job.conversation_id,
                                   spec=build_spec())
    await session.commit()
    runtime.update_draft(draft)
    await collect(session, user, draft, collection_result(build_spec()))
    await session.commit()

    finished = await jobs.enqueue(session, user_id=user.id, kind="preview",
        draft_id=draft.id, revision=draft.spec_revision)
    await jobs.finish(session, finished, "succeeded", result={})
    await session.commit()

    async def existing(session_, user_, draft_id):
        return finished

    monkeypatch.setattr(drafts, "start_preview", existing)
    arguments = json.dumps({"draft_id": str(draft.id), "spec_revision": draft.spec_revision})
    context = ToolContext(context=runtime, tool_name="preview_monitor",
                          tool_call_id="preview", tool_arguments=arguments)
    response = await preview_monitor.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert "error" not in response, response
    assert response["spec_revision"] == draft.spec_revision
    assert "rule_simulation" in response and response["rule_simulation"]["rule_state"]
    assert response["final_url"] == draft.spec["url"]
    assert response["coverage"]["scope"] == "full"
    assert isinstance(response["evidence_refs"], list)
    assert response["expires_at"]
