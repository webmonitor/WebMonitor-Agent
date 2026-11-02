"""Snapshots, definition versions, rename and archive keep their contracts."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from webmonitor.errors import DomainError
from webmonitor.models import (
    Conversation,
    Draft,
    Job,
    Monitor,
    NotificationGroup,
    Snapshot,
    User,
    utc_now,
)
from webmonitor.schemas.monitors import DraftSpec, content_hash
from webmonitor.security.auth import CurrentUser
from webmonitor.services import drafts, jobs, monitors
from webmonitor.services.notifications import load_recipients, recipients_emails


def build_spec(group_id, name="Price watch") -> DraftSpec:
    return DraftSpec.model_validate({
        "name": name,
        "url": "https://8.8.8.8/product",
        "collection_mode": "http",
        "fields": [{"name": "current_price", "type": "money", "semantic": "Price",
                    "selector": ".price",
                    "normalize": {"decimal_separator": ".", "currency": "USD"}}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "number_percent_change", "field": "current_price",
             "operator": "decrease_gte", "value": 10}]},
        "schedule": {"interval_seconds": 60, "timezone": "UTC"},
        "notification_group_ids": [str(group_id)],
        "coverage": {"scope": "full", "description": "Single price element"},
    })


async def seed(session):
    user = User(email=f"{uuid4().hex}@example.com", display_name="Owner",
                password_hash="not-a-login-hash", role="admin")
    session.add(user)
    await session.flush()
    group = NotificationGroup(name=f"Ops {uuid4().hex}", members=[
        {"email": "ops@example.com", "active": True}], created_by_user_id=user.id)
    session.add(group)
    await session.flush()
    return user, group


async def publish(session, current, user, group, name="Price watch"):
    conversation = Conversation(user_id=user.id, title=name)
    session.add(conversation)
    await session.flush()
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id,
                                    spec=build_spec(group.id, name))
    spec = DraftSpec.model_validate(draft.spec)
    recipients = recipients_emails(await load_recipients(session, spec.notification_group_ids))
    await drafts.save_preview(session, draft, {
        "revision": draft.revision,
        "spec_hash": content_hash(spec),
        "extracted_data": {"current_price": {"amount": "100", "currency": "USD"}},
        "coverage": {"scope": "full", "description": "Single price element"},
        "final_url": spec.url,
        "evidence_refs": [],
        "rule_simulation": {"triggered": False},
        "rendered_emails": [],
        "recipients": recipients,
        "recipient_sources": [{"email": email, "group_ids": [str(group.id)]}
                              for email in recipients],
        "warnings": [],
    }, ttl_minutes=60)
    monitor = await drafts.publish_draft(session, current, conversation_id=conversation.id,
        draft_id=draft.id, revision=draft.revision,
        preview_hash=draft.preview_hash or "0" * 64)
    await session.commit()
    return monitor, conversation, draft


async def add_snapshot(session, monitor, minute: int, amount: str) -> Snapshot:
    job = Job(user_id=monitor.user_id, kind="production", status="succeeded",
              monitor_id=monitor.id, revision=monitor.spec_version)
    session.add(job)
    await session.flush()
    snapshot = Snapshot(monitor_id=monitor.id, job_id=job.id,
        spec_version=monitor.spec_version, final_url=monitor.url,
        extracted_data={"current_price": {"amount": amount, "currency": "USD"}},
        coverage={"scope": "full", "description": "Single price element"},
        rule_state={}, evidence_refs=[],
        collected_at=utc_now() + timedelta(minutes=minute))
    session.add(snapshot)
    await session.flush()
    return snapshot


@pytest.mark.asyncio
async def test_snapshots_are_listed_newest_first_and_detail_names_the_monitor(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    monitor, _, _ = await publish(session, current, user, group)
    older = await add_snapshot(session, monitor, 1, "100")
    newer = await add_snapshot(session, monitor, 2, "90")
    await session.commit()

    page = await monitors.list_snapshots(session, current, monitor.id, 10, 0)
    assert [row.id for row in page.items] == [newer.id, older.id]
    assert page.total == 2

    detail = await monitors.read_snapshot(session, current, older.id)
    assert detail.monitor_id == monitor.id
    assert detail.monitor_name == monitor.name
    assert detail.extracted_data["current_price"]["amount"] == "100"

    stranger = User(email=f"{uuid4().hex}@example.com", display_name="Other",
                    password_hash="x", role="member")
    session.add(stranger)
    await session.flush()
    with pytest.raises(DomainError) as denied:
        await monitors.read_snapshot(session, CurrentUser(user_id=stranger.id, role="member"),
                                     older.id)
    assert denied.value.code == "forbidden"


@pytest.mark.asyncio
async def test_definition_versions_number_published_drafts(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    monitor, _, _ = await publish(session, current, user, group)

    conversation, draft = await drafts.draft_from_monitor(session, current, monitor.id)
    spec = DraftSpec.model_validate(draft.spec)
    recipients = recipients_emails(await load_recipients(session, spec.notification_group_ids))
    await drafts.save_preview(session, draft, {
        "revision": draft.revision, "spec_hash": content_hash(spec),
        "extracted_data": {"current_price": {"amount": "100", "currency": "USD"}},
        "coverage": {"scope": "full", "description": "Single price element"},
        "final_url": spec.url, "evidence_refs": [], "rule_simulation": {},
        "rendered_emails": [], "recipients": recipients,
        "recipient_sources": [{"email": email, "group_ids": [str(group.id)]}
                              for email in recipients],
        "warnings": [],
    }, ttl_minutes=60)
    await drafts.publish_draft(session, current, conversation_id=conversation.id,
        draft_id=draft.id, revision=draft.revision,
        preview_hash=draft.preview_hash or "0" * 64)
    await session.commit()

    page = await monitors.list_spec_versions(session, current, monitor.id, 10, 0)
    assert page.total == 2
    assert [row.version for row in page.items] == [2, 1]
    assert page.items[0].current is True
    assert page.items[1].current is False


@pytest.mark.asyncio
async def test_rename_updates_the_stored_spec_without_a_new_version(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    monitor, _, _ = await publish(session, current, user, group)

    renamed = await monitors.rename_monitor(session, current, monitor.id, "  New name  ")
    await session.commit()

    assert renamed.name == "New name"
    assert renamed.spec["name"] == "New name"
    assert renamed.spec_version == 1
    assert renamed.spec_hash == content_hash(DraftSpec.model_validate(renamed.spec))


@pytest.mark.asyncio
async def test_archive_pauses_and_cancels_but_keeps_history(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    monitor, _, _ = await publish(session, current, user, group)
    snapshot = await add_snapshot(session, monitor, 1, "100")
    pending = await jobs.enqueue(session, user_id=user.id, kind="production",
        monitor_id=monitor.id, url=monitor.url, spec=monitor.spec,
        revision=monitor.spec_version)
    await session.commit()

    archived = await monitors.archive_monitor(session, current, monitor.id)
    await session.commit()

    assert archived.archived_at is not None
    assert archived.status == "paused"
    assert pending.status == "cancelled"
    assert await session.get(Snapshot, snapshot.id) is not None
    active = await monitors.list_monitors(session, current, 50, 0)
    assert active.total == 0
    stored = await monitors.list_monitors(session, current, 50, 0, archived=True)
    assert [row.id for row in stored.items] == [monitor.id]

    restored = await monitors.restore_monitor(session, current, monitor.id)
    await session.commit()
    assert restored.archived_at is None
    assert restored.status == "paused"
    assert (await monitors.list_monitors(session, current, 50, 0)).total == 1
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1
    assert await session.scalar(select(func.count()).select_from(Draft)) == 1
