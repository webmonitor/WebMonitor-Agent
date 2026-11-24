"""Operational metrics aggregate real job and delivery state for administrators."""
from datetime import timedelta
from uuid import uuid4

import pytest

from tests.integration import support
from webmonitor.errors import DomainError
from webmonitor.models import Delivery, Event, Job, utc_now
from webmonitor.security.auth import CurrentUser
from webmonitor.services import metrics


@pytest.mark.asyncio
async def test_system_metrics_aggregate_queue_collection_delivery_and_usage(session):
    user, current, group = await support.seed_owner(session)
    conversation, draft, current = await support.prepare_draft(session, user, group)
    monitor = await support.publish(session, conversation, draft, current)
    now = utc_now()

    def job(kind, status, *, mode=None, result=None, duration=1):
        row = Job(user_id=user.id, kind=kind, status=status,
            monitor_id=monitor.id if kind == "production" else None,
            conversation_id=conversation.id if kind == "agent" else None,
            revision=1 if kind == "production" else None,
            spec={"collection_mode": mode} if mode else None, result=result,
            started_at=now - timedelta(seconds=duration) if status != "queued" else None,
            finished_at=now if status in ("succeeded", "failed") else None)
        session.add(row)
        return row

    http_ok = job("production", "succeeded", mode="http", duration=1)
    job("production", "failed", mode="http", duration=3)
    job("production", "succeeded", mode="browser", duration=2)
    job("production", "running", mode="browser")
    job("agent", "queued")
    usage = {"requests": 2, "input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    job("agent", "succeeded", result={"usage": usage})
    job("agent", "failed", result={"usage": {"requests": 1, "input_tokens": 50,
        "output_tokens": 25, "total_tokens": 75}})
    await session.flush()
    event = Event(monitor_id=monitor.id, job_id=http_ok.id, type="content_changed", change={})
    session.add(event)
    await session.flush()
    for status in ("queued", "sent", "failed", "cancelled"):
        session.add(Delivery(user_id=user.id, monitor_id=monitor.id, event_id=event.id,
            channel="webhook", recipient=f"https://example.com/{status}", subject="test",
            body_text="{}", payload={}, status=status))
    await session.flush()

    result = await metrics.system_metrics(session, current, 24)
    assert [(row.kind, row.queued, row.running) for row in result.queue] == [
        ("agent", 1, 0), ("analyze", 0, 0), ("preview", 0, 0), ("production", 0, 1)]
    http, browser = result.collection
    assert (http.succeeded, http.failed, http.success_rate) == (1, 1, 0.5)
    assert http.average_duration_ms == 2000
    assert (browser.succeeded, browser.failed, browser.success_rate) == (1, 0, 1.0)
    assert result.deliveries.active == 1
    assert result.deliveries.failure_rate == 0.5
    assert result.deliveries.cancelled == 1
    assert len(result.usage) == 1
    tokens = result.usage[0]
    assert (tokens.requests, tokens.input_tokens, tokens.output_tokens, tokens.total_tokens) == (3, 150, 75, 225)

    with pytest.raises(DomainError) as raised:
        await metrics.system_metrics(session, CurrentUser(uuid4(), role="member"), 24)
    assert raised.value.code == "forbidden"
