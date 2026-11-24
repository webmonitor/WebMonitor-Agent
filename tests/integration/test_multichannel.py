"""Dual-channel previews, event routing and per-delivery authorization stay aligned."""
import pytest
from sqlalchemy import select

from tests.integration import support
from webmonitor.models import Delivery, Event, Job, utc_now
from webmonitor.services import notifications


@pytest.mark.asyncio
async def test_dual_channel_preview_publish_and_failure_routing(session):
    user, current, group = await support.seed_owner(session)
    settings = support.build_settings(group.id).model_copy(update={
        "channel": "both",
        "webhook_url": "https://hooks.example.com/ops",
        "event_channels": {"run_failed": "webhook"},
    })
    conversation, draft, current = await support.prepare_draft(
        session, user, group, settings=settings)
    preview = draft.delivery_preview
    assert preview["channel"] == "both"
    assert preview["webhook_body"]["event"]["type"] == "content_changed"
    assert preview["rendered_emails"]
    assert preview["recipients"] == ["ops@example.com"]
    monitor = await support.publish(session, conversation, draft, current)
    assert monitor.delivery_channel == "both"
    assert monitor.event_channels == {"run_failed": "webhook"}
    assert monitor.approved_recipients

    job = Job(user_id=user.id, kind="production", status="succeeded", monitor_id=monitor.id,
        revision=1, url=monitor.url, spec=monitor.spec, finished_at=utc_now())
    session.add(job)
    await session.flush()
    events = {}
    for event_type in ("content_changed", "run_failed"):
        event = Event(monitor_id=monitor.id, job_id=job.id, type=event_type, change={})
        session.add(event)
        await session.flush()
        await notifications.enqueue_event_deliveries(session, monitor, event, {})
        events[event_type] = event
    deliveries = (await session.scalars(select(Delivery))).all()
    by_event = {event_type: [row.channel for row in deliveries if row.event_id == event.id]
                for event_type, event in events.items()}
    assert sorted(by_event["content_changed"]) == ["email", "webhook"]
    assert by_event["run_failed"] == ["webhook"]
    for row in deliveries:
        assert await notifications.authorized(session, row) is True

    monitor.event_channels = {"run_failed": "email"}
    failed_webhook = next(row for row in deliveries if row.event_id == events["run_failed"].id)
    assert await notifications.authorized(session, failed_webhook) is False
    content_webhook = next(row for row in deliveries
        if row.event_id == events["content_changed"].id and row.channel == "webhook")
    assert await notifications.authorized(session, content_webhook) is True
