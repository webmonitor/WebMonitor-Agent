"""Recipient consent, preview identity, editing and cancellation regressions."""
import asyncio
import json
from datetime import timedelta

import pytest
from agents import RunContextWrapper
from agents.tool_context import ToolContext
from sqlalchemy import select
from support import (
    COVERAGE,
    build_spec,
    collect,
    collection_result,
    extracted,
    prepare_draft,
    publish,
    seed_owner,
)
from test_runs import make_monitor, running_job

from webmonitor import worker
from webmonitor.agent.orchestration import _context, _instructions
from webmonitor.agent.tools import save_monitor_draft
from webmonitor.errors import DomainError
from webmonitor.models import Draft, EmailDelivery, Job, NotificationGroup, utc_now
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.security.auth import CurrentUser
from webmonitor.services import conversations, drafts, jobs, monitors, notifications, runs


async def approved_monitor(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    monitor = await publish(session, conversation, draft, current)
    await session.commit()
    return user, group, current, conversation, draft, monitor


async def changed_event(session, monitor):
    async def collect(state):
        job = await jobs.enqueue(session, user_id=monitor.user_id, kind="production",
            monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url, spec=monitor.spec)
        await session.commit()
        await jobs.claim(session, kind="production", worker_id="notifications-regression")
        await runs.commit_success(session, job, {"final_url": monitor.url,
            "fields": extracted(state=state), "coverage": COVERAGE, "evidence_refs": []})
        await session.commit()
    await collect("Open")
    await collect("Closed")
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
    user, current, group = await seed_owner(session)
    second = NotificationGroup(name="Also approved", created_by_user_id=user.id,
        members=[{"email": "ops@example.com", "active": True}])
    session.add(second)
    await session.flush()
    both = DeliverySettings(notification_group_ids=[group.id, second.id],
        schedule={"interval_seconds": 60, "timezone": "UTC"})
    conversation, draft, _ = await prepare_draft(session, user, group, settings=both)
    monitor = await publish(session, conversation, draft, current)
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
    user, _, current, _, _, monitor = await approved_monitor(session)
    edit_conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    spec = build_spec(url="https://8.8.8.8/notice?page=2")
    edit = await drafts.save_spec(session, current, conversation_id=edit_conversation.id,
                                  spec=spec, draft_id=edit.id)
    await collect(session, user, edit, collection_result(spec))
    old_extraction = edit.extraction_preview_hash
    await collect(session, user, edit, collection_result(spec, state="Closed"))
    assert edit.extraction_preview_hash != old_extraction
    with pytest.raises(DomainError) as stale:
        await drafts.publish_draft(session, current, conversation_id=edit_conversation.id,
            draft_id=edit.id, spec_revision=edit.spec_revision,
            settings_revision=edit.settings_revision,
            extraction_preview_hash=old_extraction,
            delivery_preview_hash=edit.delivery_preview_hash or "0" * 64)
    assert stale.value.code == "preview_stale"
    assert monitor.spec_version == 1
    await drafts.publish_draft(session, current, conversation_id=edit_conversation.id,
        draft_id=edit.id, spec_revision=edit.spec_revision,
        settings_revision=edit.settings_revision,
        extraction_preview_hash=edit.extraction_preview_hash or "0" * 64,
        delivery_preview_hash=edit.delivery_preview_hash or "0" * 64)
    assert monitor.spec_version == 2


@pytest.mark.asyncio
async def test_preview_status_survives_failure_and_does_not_replace_agent_status(session):
    _, _, current, conversation, draft, _ = await approved_monitor(session)
    preview = await jobs.enqueue(session, user_id=current.user_id, kind="preview",
        conversation_id=conversation.id, draft_id=draft.id, revision=draft.spec_revision)
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
    edited = runtime.draft_spec.model_copy(update={"coverage":
        runtime.draft_spec.coverage.model_copy(update={"description": "Wider sweep"})})
    arguments = json.dumps({"spec": edited.model_dump(mode="json")})
    context = ToolContext(context=runtime, tool_name="save_monitor_draft",
        tool_call_id="edit", tool_arguments=arguments)
    response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert "error" not in response, response
    await session.refresh(draft)
    assert draft.monitor_id == monitor.id
    assert draft.spec["coverage"]["description"] == "Wider sweep"
    rows = (await session.scalars(select(Draft).where(Draft.conversation_id == conversation.id))).all()
    assert [row.id for row in rows] == [draft.id]
    assert runtime.spec_revision == draft.spec_revision
    await drafts.save_spec(session, current, conversation_id=conversation.id,
        draft_id=draft.id, spec=build_spec())
    await session.commit()
    stale_response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(stale_response, str):
        stale_response = json.loads(stale_response)
    assert stale_response["error"]["code"] == "stale_revision"
    await session.refresh(draft)
    assert draft.spec["coverage"]["description"] == "Whole notice list"


@pytest.mark.asyncio
async def test_cancelled_production_lease_is_terminal_and_does_not_fail_monitor(session):
    user, _, group = await seed_owner(session)
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
    user, _, group = await seed_owner(session)
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
