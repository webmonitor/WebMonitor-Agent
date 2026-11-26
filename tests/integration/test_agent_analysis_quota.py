"""Agent discovery and MCP discovery share one persistent hourly analysis budget."""
import json

import pytest
from agents.tool_context import ToolContext
from sqlalchemy import select

from tests.integration.test_agent_tools import _runtime, running_agent_job
from webmonitor.agent.tools import (
    analyze_target,
    capture_network,
    probe_target,
    replay_request,
)
from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.mcp.tools_discover import _enqueue_analyze
from webmonitor.models import Job
from webmonitor.services import jobs


def _payload(response):
    return json.loads(response) if isinstance(response, str) else response


def _context(user, job, name, arguments):
    encoded = json.dumps(arguments)
    return ToolContext(
        context=_runtime(user, job),
        tool_name=name,
        tool_call_id=f"call-{name}",
        tool_arguments=encoded,
    ), encoded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "name", "arguments", "mode", "op"),
    [
        (analyze_target, "analyze_target", {"url": "https://8.8.8.8/page"}, "http", None),
        (capture_network, "capture_network", {"url": "https://8.8.8.8/page"}, "browser", "network"),
        (probe_target, "probe_target", {"url": "https://8.8.8.8/page"}, "http", "probe"),
        (
            replay_request,
            "replay_request",
            {"request": {"method": "GET", "url": "https://8.8.8.8/api"}},
            "http",
            "replay",
        ),
    ],
    ids=["analyze", "network", "probe", "replay"],
)
async def test_agent_discovery_persists_jobs_and_consumes_the_mcp_quota(
    session, monkeypatch, tool, name, arguments, mode, op
):
    user, agent_job = await running_agent_job(session)
    await session.commit()
    monkeypatch.setenv("ANALYZE_RUNS_PER_HOUR", "1")
    get_settings.cache_clear()

    async def finish_analysis(job_id, **kwargs):
        async with get_session_factory()() as child_session:
            finished = await child_session.get(Job, job_id)
            result = {"final_url": finished.url, "analysis": {"selectors": ["h1"]}}
            if (finished.spec or {}).get("op") == "probe":
                result = {"probe": {"status": 200, "final_url": finished.url}}
            elif (finished.spec or {}).get("op") == "replay":
                result = {"replay": {"status": 200, "final_url": finished.url}}
            await jobs.finish(child_session, finished, "succeeded", result=result)
            await child_session.commit()
            return finished

    monkeypatch.setattr(jobs, "wait", finish_analysis)
    try:
        context, encoded = _context(user, agent_job, name, arguments)
        response = _payload(await tool.on_invoke_tool(context, encoded))
        assert "error" not in response, response

        rows = (await session.scalars(
            select(Job).where(Job.kind == "analyze").execution_options(populate_existing=True)
        )).all()
        assert len(rows) == 1
        assert rows[0].status == "succeeded"
        assert rows[0].conversation_id == agent_job.conversation_id
        assert rows[0].spec["collection_mode"] == mode
        assert rows[0].spec.get("op") == op

        # The MCP path sees the Agent row even though it is terminal: hourly
        # quotas count real work, not just currently queued jobs.
        with pytest.raises(DomainError) as raised:
            await _enqueue_analyze(
                user_id=user.id,
                url="https://8.8.8.8/from-mcp",
                spec={"collection_mode": "http", "op": "probe"},
            )
        assert raised.value.code == "rate_limited"
        assert raised.value.details["limit"] == 1
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mcp_analysis_limits_agent_work_but_agent_cache_hit_is_free(
    session, monkeypatch
):
    user, agent_job = await running_agent_job(session)
    await session.commit()
    monkeypatch.setenv("ANALYZE_RUNS_PER_HOUR", "1")
    get_settings.cache_clear()
    try:
        created = await _enqueue_analyze(
            user_id=user.id,
            url="https://8.8.8.8/cached",
            spec={"collection_mode": "http"},
        )
        async with get_session_factory()() as child_session:
            cached = await child_session.get(Job, created.id)
            cached.conversation_id = agent_job.conversation_id
            await jobs.finish(
                child_session,
                cached,
                "succeeded",
                result={"analysis": {"source": "mcp"}, "coverage": {"scope": "full"}},
            )
            await child_session.commit()

        context, encoded = _context(
            user, agent_job, "analyze_target", {"url": "https://8.8.8.8/cached"}
        )
        reused = _payload(await analyze_target.on_invoke_tool(context, encoded))
        assert "error" not in reused, reused
        assert reused["job_id"] == str(created.id)
        assert reused["analysis"] == {"source": "mcp"}

        context, encoded = _context(
            user, agent_job, "capture_network", {"url": "https://8.8.8.8/new-work"}
        )
        limited = _payload(await capture_network.on_invoke_tool(context, encoded))
        assert limited["error"]["code"] == "rate_limited"

        rows = (await session.scalars(
            select(Job).where(Job.kind == "analyze").execution_options(populate_existing=True)
        )).all()
        assert [item.id for item in rows] == [created.id]
    finally:
        get_settings.cache_clear()
