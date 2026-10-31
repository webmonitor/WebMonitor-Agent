"""Recipient consent, preview identity, editing and cancellation regressions."""
import asyncio
import json
from datetime import timedelta

import pytest
from agents import RunContextWrapper
from agents.tool_context import ToolContext
from sqlalchemy import select
from test_publish_flow import _conversation, build_spec, preview_payload, seed
from test_runs import make_monitor, running_job

from webmonitor import worker
from webmonitor.agent.orchestration import _context, _instructions
from webmonitor.agent.tools import save_monitor_draft
from webmonitor.errors import DomainError
from webmonitor.models import Draft, EmailDelivery, Job, NotificationGroup, utc_now
from webmonitor.security.auth import CurrentUser
from webmonitor.services import conversations, drafts, jobs, monitors, notifications, runs


async def approved_monitor(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await _conversation(session, user)
    spec = build_spec(group.id)
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id, spec=spec)
    await drafts.save_preview(session, draft, preview_payload(spec, draft, ["ops@example.com"], "100"),
                              ttl_minutes=60)
    monitor = await drafts.publish_draft(session, current, conversation_id=conversation.id,
        draft_id=draft.id, revision=draft.revision, preview_hash=draft.preview_hash)
    await session.commit()
    return user, group, current, conversation, draft, monitor


async def changed_event(session, monitor):
    async def collect(amount):
        job = await jobs.enqueue(session, user_id=monitor.user_id, kind="production",
            monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url, spec=monitor.spec)
        await session.commit()
        await jobs.claim(session, kind="production", worker_id="notifications-regression")
        await runs.commit_success(session, job, {"final_url": monitor.url,
            "fields": {"current_price": {"amount": amount, "currency": "USD"}},
            "coverage": {"scope": "full", "description": "Single price"}, "evidence_refs": []})
        await session.commit()
    await collect("100")
    await collect("80")
    return (await session.scalars(select(EmailDelivery))).all()


@pytest.mark.asyncio
async def test_new_group_member_needs_approval_and_unrelated_group_cannot_authorize(session):
    user, group, _, _, _, monitor = await approved_monitor(session)
    group.members = [*group.members, {"email": "new@example.com", "active": True}]
    await session.commit()
    deliveries = await changed_event(session, monitor)
    assert [delivery.recipient for delivery in deliveries] == ["ops@example.com"]
    delivery = deliveries[0]
    assert await notifications.authorized(session, delivery)
    unrelated = NotificationGroup(name="Unrelated", created_by_user_id=user.id,
        members=[{"email": "ops@example.com", "active": True}])
    session.add(unrelated)
    group.members = [{"email": "new@example.com", "active": True}]
    await session.commit()
    assert not await notifications.authorized(session, delivery)


@pytest.mark.asyncio
async def test_another_approved_group_preserves_recipient_authority(session):
    user, group = await seed(session)
    second = NotificationGroup(name="Also approved", created_by_user_id=user.id,
        members=[{"email": "ops@example.com", "active": True}])
    session.add(second)
    await session.flush()
    spec = build_spec(group.id).model_copy(update={"notification_group_ids": [group.id, second.id]})
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await _conversation(session, user)
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id, spec=spec)
    await drafts.save_preview(session, draft, preview_payload(spec, draft, ["ops@example.com"], "100"),
                              ttl_minutes=60)
    monitor = await drafts.publish_draft(session, current, conversation_id=conversation.id,
        draft_id=draft.id, revision=draft.revision, preview_hash=draft.preview_hash)
    await session.commit()
    delivery, = await changed_event(session, monitor)
    group.enabled = False
    await session.commit()
    assert await notifications.authorized(session, delivery)
    second.members = []
    await session.commit()
    assert not await notifications.authorized(session, delivery)


@pytest.mark.asyncio
async def test_replaced_preview_rejects_old_page_and_preserves_monitor(session):
    _, _, current, _, _, monitor = await approved_monitor(session)
    edit_conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    spec = build_spec(monitor.notification_group_ids[0])
    payload = preview_payload(spec, edit, ["ops@example.com"], "100")
    await drafts.save_preview(session, edit, payload, ttl_minutes=60)
    old_hash = edit.preview_hash
    await drafts.save_preview(session, edit, dict(payload), ttl_minutes=60)
    assert old_hash != edit.preview_hash
    with pytest.raises(DomainError, match="preview"):
        await drafts.publish_draft(session, current, conversation_id=edit_conversation.id,
            draft_id=edit.id, revision=edit.revision, preview_hash=old_hash)
    assert monitor.spec_version == 1
    await drafts.publish_draft(session, current, conversation_id=edit_conversation.id,
        draft_id=edit.id, revision=edit.revision, preview_hash=edit.preview_hash)
    assert monitor.spec_version == 2


@pytest.mark.asyncio
async def test_preview_status_survives_failure_and_does_not_replace_agent_status(session):
    _, _, current, conversation, draft, _ = await approved_monitor(session)
    preview = await jobs.enqueue(session, user_id=current.user_id, kind="preview",
        conversation_id=conversation.id, draft_id=draft.id, revision=draft.revision)
    await jobs.finish(session, preview, "failed", error_code="target_unavailable")
    await session.commit()
    snapshot = await conversations.snapshot(session, current, conversation.id)
    assert [(job.kind, job.status, job.error_code) for job in snapshot.jobs] == [
        ("preview", "failed", "target_unavailable")]


@pytest.mark.asyncio
async def test_edit_context_survives_missing_history_and_save_targets_original_monitor(session):
    _, _, current, _, _, monitor = await approved_monitor(session)
    conversation, draft = await drafts.draft_from_monitor(session, current, monitor.id)
    job = await jobs.enqueue(session, user_id=current.user_id, kind="agent",
                             conversation_id=conversation.id)
    await session.commit()
    await jobs.claim(session, kind="agent", worker_id="edit-regression")
    await session.commit()
    runtime = await _context(job.id, "edit-regression")
    instructions = _instructions(RunContextWrapper(context=runtime), None)
    assert str(draft.id) in instructions and str(monitor.id) in instructions
    assert runtime.draft_spec.url == monitor.url
    edited = runtime.draft_spec.model_copy(update={"schedule":
        runtime.draft_spec.schedule.model_copy(update={"interval_seconds": 600})})
    arguments = json.dumps({"spec": edited.model_dump(mode="json")})
    context = ToolContext(context=runtime, tool_name="save_monitor_draft",
        tool_call_id="edit", tool_arguments=arguments)
    response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert "error" not in response, response
    await session.refresh(draft)
    assert draft.monitor_id == monitor.id and draft.spec["schedule"]["interval_seconds"] == 600
    rows = (await session.scalars(select(Draft).where(Draft.conversation_id == conversation.id))).all()
    assert [row.id for row in rows] == [draft.id]
    assert runtime.draft_revision == draft.revision
    await drafts.save_draft(session, current, conversation_id=conversation.id,
        draft_id=draft.id, spec=build_spec(monitor.notification_group_ids[0]))
    await session.commit()
    stale_response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(stale_response, str):
        stale_response = json.loads(stale_response)
    assert stale_response["error"]["code"] == "stale_revision"
    await session.refresh(draft)
    assert draft.spec["schedule"]["interval_seconds"] == 60


@pytest.mark.asyncio
async def test_cancelled_production_lease_is_terminal_and_does_not_fail_monitor(session):
    user, group = await seed(session)
    monitor = await make_monitor(session, user, group)
    live = await running_job(session, monitor)
    live.cancel_requested_at = utc_now()
    live.lease_expires_at = utc_now() - timedelta(seconds=1)
    await session.commit()
    assert await jobs.claim(session, kind="production", worker_id="reaper") is None
    await session.commit()
    await session.refresh(live)
    await session.refresh(monitor)
    assert live.status == "cancelled" and live.lease_owner is None
    assert monitor.health_status == "healthy"
    assert not (await session.scalars(select(EmailDelivery))).all()


@pytest.mark.asyncio
async def test_cancel_one_collection_keeps_slot_usable_for_next_job(session, monkeypatch):
    user, group = await seed(session)
    first = await make_monitor(session, user, group)
    second = await make_monitor(session, user, group)
    first.spec = {**first.spec, "url": "https://8.8.8.8/first"}
    first.url = first.spec["url"]
    second.spec = {**second.spec, "url": "https://8.8.8.8/second"}
    second.url = second.spec["url"]
    for monitor in (first, second):
        await jobs.enqueue(session, user_id=user.id, kind="production", monitor_id=monitor.id,
            revision=1, url=monitor.url, spec=monitor.spec)
    await session.commit()
    started, continued = asyncio.Event(), asyncio.Event()

    async def collection(url, spec):
        if url.endswith("/first"):
            started.set()
            await asyncio.Event().wait()
        continued.set()
        raise DomainError("collection_invalid", 422)

    monkeypatch.setattr(worker, "collect_http", collection)
    monkeypatch.setattr(worker, "RENEW_SECONDS", 0.01)
    slot = asyncio.create_task(worker._collection_slot("cancellation-regression", "http"))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        await monitors.pause_monitor(session, CurrentUser(user_id=user.id, role="admin"), first.id)
        await session.commit()
        await asyncio.wait_for(continued.wait(), timeout=5)
        assert not slot.done()
        stored = await session.scalar(select(Job).where(Job.monitor_id == first.id)
                                      .execution_options(populate_existing=True))
        assert stored.status == "cancelled"
    finally:
        slot.cancel()
        await asyncio.gather(slot, return_exceptions=True)
    assert slot.cancelled()
