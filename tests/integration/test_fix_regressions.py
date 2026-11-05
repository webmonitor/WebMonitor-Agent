"""Recipient consent, preview identity, editing and cancellation regressions."""
import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace

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
from webmonitor.models import (
    Draft,
    Delivery,
    Event,
    Job,
    Monitor,
    NotificationGroup,
    utc_now,
)
from webmonitor.schemas.api import GroupPatch
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
    return (await session.scalars(select(Delivery))).all()


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
    assert not (await session.scalars(select(Delivery))).all()


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


@pytest.mark.asyncio
async def test_republishing_with_a_new_group_refreshes_approved_recipients(session):
    user, _, current, _, _, monitor = await approved_monitor(session)
    replacement = NotificationGroup(name="Night shift", created_by_user_id=user.id,
        members=[{"email": "night@example.com", "active": True}])
    session.add(replacement)
    await session.flush()

    conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    edit = await drafts.save_settings(session, current, draft_id=edit.id,
        revision=edit.settings_revision,
        settings=DeliverySettings(notification_group_ids=[replacement.id],
            schedule={"interval_seconds": 60, "timezone": "UTC"}))
    await collect(session, user, edit, collection_result(build_spec()))
    await session.commit()
    await publish(session, conversation, edit, current)
    await session.commit()

    stored = await session.get(Monitor, monitor.id)
    assert [item["email"] for item in stored.approved_recipients] == ["night@example.com"]

    publish_job = await jobs.enqueue(session, user_id=user.id, kind="production",
        monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url,
        spec=monitor.spec)
    await session.flush()
    event = Event(monitor_id=monitor.id, job_id=publish_job.id,
                  type="content_changed", change={})
    session.add(event)
    await session.flush()
    await notifications.enqueue_event_deliveries(session, stored, event, extracted())
    await session.commit()
    recipients = sorted(delivery.recipient for delivery in
                        (await session.scalars(select(Delivery))).all())
    assert recipients == ["night@example.com"]


@pytest.mark.asyncio
async def test_archived_monitor_cannot_be_resumed(session):
    _, _, current, _, _, monitor = await approved_monitor(session)
    await monitors.archive_monitor(session, current, monitor.id)
    await session.commit()
    with pytest.raises(DomainError) as archived:
        await monitors.resume_monitor(session, current, monitor.id)
    assert archived.value.code == "monitor_archived"

    # Even a direct status write cannot make an archived monitor run again.
    monitor.status = "active"
    monitor.next_run_at = utc_now() - timedelta(seconds=1)
    await session.commit()
    assert await runs.schedule_due(session) == 0


@pytest.mark.asyncio
async def test_contract_change_cancels_the_in_flight_collection(session):
    user, _, current, _, _, monitor = await approved_monitor(session)
    in_flight = await jobs.enqueue(session, user_id=user.id, kind="production",
        monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url,
        spec=monitor.spec)
    await session.commit()

    conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    spec = build_spec(url="https://8.8.8.8/notice?page=2")
    edit = await drafts.save_spec(session, current, conversation_id=conversation.id,
                                  spec=spec, draft_id=edit.id)
    await collect(session, user, edit, collection_result(spec))
    await session.commit()
    await publish(session, conversation, edit, current)
    await session.commit()

    stored = await session.get(Job, in_flight.id)
    assert stored.status == "cancelled"
    assert monitor.spec_version == 2
    assert monitor.next_run_at <= utc_now() + timedelta(seconds=61)


@pytest.mark.asyncio
async def test_delivery_attempts_stop_at_the_configured_limit(session, monkeypatch):
    from webmonitor.config import get_settings

    _, _, _, _, _, monitor = await approved_monitor(session)
    deliveries = await changed_event(session, monitor)
    delivery = deliveries[0]
    delivery.attempt_count = get_settings().max_attempts
    delivery.available_at = utc_now() - timedelta(seconds=1)
    await session.commit()

    assert await notifications.claim_delivery(session, "mailer") is None
    await session.commit()
    stored = await session.get(Delivery, delivery.id, populate_existing=True)
    assert stored.status == "failed"
    assert stored.error_code == "delivery_attempts_exhausted"
    assert stored.lease_owner is None


@pytest.mark.asyncio
async def test_unexpected_delivery_fault_does_not_leave_the_row_sending(session, monkeypatch):
    _, _, _, _, _, monitor = await approved_monitor(session)
    delivery = (await changed_event(session, monitor))[0]
    delivery.available_at = utc_now() - timedelta(seconds=1)
    await session.commit()
    claimed = await notifications.claim_delivery(session, "mailer")
    await session.commit()
    assert claimed is not None

    async def broken(delivery, rendered):
        raise RuntimeError("smtp client exploded")

    monkeypatch.setattr(worker, "send_email", broken)
    await worker._deliver(claimed, "mailer")
    stored = await session.get(Delivery, delivery.id, populate_existing=True)
    assert stored.status == "failed"
    assert stored.error_code == "delivery_aborted"
    assert stored.lease_owner is None


@pytest.mark.asyncio
async def test_a_cancelled_child_wait_cancels_the_child_job(session):
    user, _, _, _, _, _ = await approved_monitor(session)
    child = await jobs.enqueue(session, user_id=user.id, kind="analyze",
        url="https://8.8.8.8/page", spec={"collection_mode": "http"})
    await session.commit()
    waiter = asyncio.create_task(jobs.wait(child.id, timeout=30, cancel_on_timeout=True))
    await asyncio.sleep(0.3)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    stored = await session.get(Job, child.id, populate_existing=True)
    assert stored.status == "cancelled"


@pytest.mark.asyncio
async def test_a_group_used_by_a_live_monitor_cannot_be_deleted(session):
    user, group, current, _, _, monitor = await approved_monitor(session)
    with pytest.raises(DomainError) as used:
        await notifications.disable_group(session, current, group.id)
    assert used.value.code == "group_in_use"
    assert used.value.details == {"monitor_ids": [str(monitor.id)]}
    with pytest.raises(DomainError) as patch_used:
        await notifications.write_group(session, current,
            GroupPatch(enabled=False), group_id=group.id)
    assert patch_used.value.code == "group_in_use"

    await monitors.archive_monitor(session, current, monitor.id)
    await session.commit()
    await notifications.disable_group(session, current, group.id)
    await session.commit()
    assert (await session.get(NotificationGroup, group.id)).deleted_at is not None


@pytest.mark.asyncio
async def test_group_members_are_hidden_from_members_but_counted(session):
    user, group, current, _, _, _ = await approved_monitor(session)
    group.members = [{"email": "ops@example.com", "active": True},
                     {"email": "quiet@example.com", "active": False}]
    await session.commit()

    admin_page = await notifications.list_groups(session, 50, 0, include_members=True)
    assert admin_page.items[0].member_count == 1
    assert len(admin_page.items[0].members) == 2
    member_page = await notifications.list_groups(session, 50, 0, include_members=False)
    assert member_page.items[0].members == []
    assert member_page.items[0].member_count == 1


@pytest.mark.asyncio
async def test_published_draft_cannot_be_previewed_again(session):
    _, _, current, conversation, draft, _ = await approved_monitor(session)
    await session.commit()
    with pytest.raises(DomainError) as closed:
        await drafts.start_preview(session, current, draft.id)
    assert closed.value.code == "draft_not_editable"


@pytest.mark.asyncio
async def test_editing_after_publication_opens_a_new_draft_for_the_same_monitor(session):
    _, _, current, conversation, published, monitor = await approved_monitor(session)
    job = await jobs.enqueue(session, user_id=current.user_id, kind="agent",
                             conversation_id=conversation.id)
    await session.commit()
    await jobs.claim(session, kind="agent", worker_id="post-publish")
    await session.commit()
    runtime = await _context(job.id, "post-publish")
    edited = runtime.draft_spec.model_copy(update={"name": "Notice watch v2"})
    arguments = json.dumps({"spec": edited.model_dump(mode="json")})
    context = ToolContext(context=runtime, tool_name="save_monitor_draft",
        tool_call_id="post-publish", tool_arguments=arguments)
    response = await save_monitor_draft.on_invoke_tool(context, arguments)
    if isinstance(response, str):
        response = json.loads(response)
    assert "error" not in response, response

    fresh = await session.get(Draft, uuid_of(response["draft_id"]), populate_existing=True)
    assert fresh.id != published.id
    assert fresh.monitor_id == monitor.id
    assert fresh.status == "draft"
    assert runtime.draft_id == fresh.id
    assert published.status == "published"


def uuid_of(value: str):
    from uuid import UUID
    return UUID(value)


@pytest.mark.asyncio
async def test_a_run_cancelled_while_finishing_never_reports_success(session):
    from webmonitor.agent.orchestration import _finish

    user, job = await _running_agent(session)
    await session.commit()
    job.cancel_requested_at = utc_now()
    job.partial_text = "half an answer"
    await session.commit()

    await _finish(job.id, "cancel-race", result={"usage": {}})
    stored = await session.get(Job, job.id, populate_existing=True)
    assert stored.status == "cancelled"
    assert stored.error_code == "run_cancelled"
    assert stored.partial_text == ""
    assert stored.result is None


async def _running_agent(session):
    from uuid import uuid4

    from webmonitor.models import Conversation, User

    user = User(email=f"{uuid4().hex}@example.com", display_name="Racer",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    conversation = Conversation(user_id=user.id, title="race")
    session.add(conversation)
    await session.flush()
    job = Job(user_id=user.id, kind="agent", status="running",
              conversation_id=conversation.id, lease_owner="cancel-race",
              lease_expires_at=utc_now() + timedelta(seconds=90), attempt_count=1)
    session.add(job)
    await session.flush()
    return user, job


@pytest.mark.asyncio
async def test_a_delivery_without_recipient_sources_is_cancelled_not_retried(session):
    _, _, _, _, _, monitor = await approved_monitor(session)
    delivery = (await changed_event(session, monitor))[0]
    delivery.payload = {}
    await session.commit()
    assert not await notifications.authorized(session, delivery)


@pytest.mark.asyncio
async def test_evidence_uploaded_for_a_failed_commit_is_deleted(session, monkeypatch):
    user, _, group = await seed_owner(session)
    monitor = await make_monitor(session, user, group)
    uploaded = [{"kind": "html", "bucket": "evidence", "object_key": "monitors/x/page",
                 "content_type": "text/html; charset=utf-8", "size_bytes": 5,
                 "sha256": "a" * 64}]
    deleted: list[tuple[str, str]] = []

    async def fake_upload(*, prefix, kind, data):
        return uploaded[0]

    async def fake_delete(bucket, key):
        deleted.append((bucket, key))

    async def failing_commit(*args, **kwargs):
        raise RuntimeError("database went away")

    async def fake_collect(url, spec):
        from webmonitor.collection.types import CollectionResult
        return CollectionResult(url, "<html>new</html>", None, {"title": "new"},
                                {"scope": "full", "description": "Single heading"},
                                5, [], None, body_kind="html")

    monkeypatch.setattr(worker, "upload_evidence", fake_upload)
    monkeypatch.setattr(worker, "delete_evidence", fake_delete)
    monkeypatch.setattr(worker, "collect_http", fake_collect)
    monkeypatch.setattr(worker, "runs", SimpleNamespace(commit_success=failing_commit,
                                                        fail_run=runs.fail_run))

    job = await jobs.enqueue(session, user_id=user.id, kind="production",
        monitor_id=monitor.id, revision=monitor.spec_version, url=monitor.url,
        spec=monitor.spec)
    await session.commit()
    claimed = await jobs.claim(session, kind="production", worker_id="orphans")
    await session.commit()
    assert claimed is not None
    await worker._collect(claimed.id, "orphans")
    assert deleted == [("evidence", "monitors/x/page")]
