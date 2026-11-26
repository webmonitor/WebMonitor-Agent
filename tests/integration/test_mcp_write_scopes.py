"""Write-scoped PATs must not gain read access through mutation responses."""
from uuid import UUID

import pytest
from sqlalchemy import select

from tests.integration.support import build_settings, prepare_draft, publish, seed_owner
from tests.integration.test_mcp_server import (  # noqa: F401
    _tool_json,
    mcp_app,
    open_mcp_session,
)
from webmonitor.db import get_session_factory
from webmonitor.models import Delivery, Draft, Event, Job
from webmonitor.services import jobs, tokens


@pytest.mark.asyncio
async def test_write_only_pat_cannot_read_derived_or_operation_data(
    mcp_app, session, monkeypatch  # noqa: F811 - imported pytest fixture
):
    user, current, group = await seed_owner(session)
    conversation, draft, current = await prepare_draft(session, user, group)
    monitor = await publish(session, conversation, draft, current)
    source_job = Job(
        user_id=user.id,
        kind="production",
        status="succeeded",
        monitor_id=monitor.id,
        url="https://private.example.invalid/secret",
        result={"private_result": "job-secret"},
    )
    session.add(source_job)
    await session.flush()
    event = Event(
        monitor_id=monitor.id,
        job_id=source_job.id,
        type="content_changed",
        change={"private_change": "event-secret"},
        payload={},
    )
    session.add(event)
    await session.flush()
    delivery = Delivery(
        user_id=user.id,
        monitor_id=monitor.id,
        event_id=event.id,
        recipient="private-recipient@example.com",
        subject="Private subject",
        body_text="Private body",
        payload={},
        status="failed",
    )
    session.add(delivery)
    _, raw_token = await tokens.create_token(
        session,
        current,
        name="Write only",
        scopes=["drafts:write", "monitors:write", "events:write"],
        ttl_days=30,
    )
    await session.commit()

    async def finish_with_private_result(job_id, **kwargs):
        async with get_session_factory()() as child_session:
            finished = await child_session.get(Job, job_id)
            await jobs.finish(
                child_session,
                finished,
                "succeeded",
                result={"fields": {"private_value": "must-not-leak"}},
            )
            await child_session.commit()
            return finished

    monkeypatch.setattr(
        "webmonitor.mcp.tools_ops._wait_with_progress", finish_with_private_result
    )

    async with open_mcp_session(mcp_app, raw_token) as (mcp_session, _):
        derived = await mcp_session.call_tool(
            "derive_draft_from_monitor", {"monitor_id": str(monitor.id)}
        )
        assert derived.is_error is True
        derived_payload = _tool_json(derived)
        assert derived_payload["error"]["code"] == "insufficient_scope"
        assert derived_payload["error"]["details"] == {"required_scope": "read"}
        assert "spec" not in derived_payload and "settings" not in derived_payload
        assert len((await session.scalars(select(Draft))).all()) == 1

        updated = await mcp_session.call_tool(
            "update_monitor_settings",
            {
                "monitor_id": str(monitor.id),
                "settings": build_settings(group.id, interval=120).model_dump(mode="json"),
            },
        )
        assert updated.is_error is False
        assert _tool_json(updated) == {"monitor_id": str(monitor.id), "updated": True}

        queued = await mcp_session.call_tool(
            "run_monitor_now", {"monitor_id": str(monitor.id), "wait": False}
        )
        assert queued.is_error is False
        queued_payload = _tool_json(queued)
        assert set(queued_payload) == {"job_id", "status"}
        assert queued_payload["status"] == "queued"
        assert "private.example.invalid" not in queued.content[0].text

        run = await mcp_session.call_tool(
            "run_monitor_now",
            {"monitor_id": str(monitor.id), "wait": True, "timeout_seconds": 15},
        )
        assert run.is_error is False
        run_payload = _tool_json(run)
        assert run_payload == {"job_id": queued_payload["job_id"], "status": "succeeded"}
        assert "must-not-leak" not in run.content[0].text

        renamed = await mcp_session.call_tool(
            "rename_monitor", {"monitor_id": str(monitor.id), "name": "Renamed privately"}
        )
        assert renamed.is_error is False
        assert _tool_json(renamed) == {"monitor_id": str(monitor.id), "renamed": True}

        for tool_name, status in (
            ("pause_monitor", "paused"),
            ("resume_monitor", "active"),
            ("archive_monitor", "paused"),
            ("restore_monitor", "paused"),
        ):
            outcome = await mcp_session.call_tool(
                tool_name, {"monitor_id": str(monitor.id)}
            )
            assert outcome.is_error is False
            assert _tool_json(outcome) == {"monitor_id": str(monitor.id), "status": status}
            assert "name" not in _tool_json(outcome) and "url" not in _tool_json(outcome)

        acknowledged = await mcp_session.call_tool(
            "acknowledge_event", {"event_id": str(event.id)}
        )
        assert acknowledged.is_error is False
        assert _tool_json(acknowledged) == {"event_id": str(event.id), "acknowledged": True}
        assert "event-secret" not in acknowledged.content[0].text

        retried = await mcp_session.call_tool(
            "retry_delivery", {"delivery_id": str(delivery.id)}
        )
        assert retried.is_error is False
        assert _tool_json(retried) == {"delivery_id": str(delivery.id), "status": "queued"}
        assert "private-recipient@example.com" not in retried.content[0].text
        assert "Private subject" not in retried.content[0].text

    stored = await session.get(Job, UUID(run_payload["job_id"]))
    assert stored.result["fields"]["private_value"] == "must-not-leak"
