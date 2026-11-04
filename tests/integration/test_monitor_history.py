"""Snapshots, definition versions, rename and archive keep their contracts."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from support import COVERAGE, build_settings, build_spec, collection_result, collect
from support import conversation_for, extracted
from support import publish as publish_draft
from webmonitor.errors import DomainError
from webmonitor.models import (
    Draft,
    Job,
    Monitor,
    NotificationGroup,
    Snapshot,
    User,
    utc_now,
)
from webmonitor.schemas.monitors import MonitorSpec, content_hash
from webmonitor.security.auth import CurrentUser
from webmonitor.services import drafts, jobs, monitors


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


async def publish(session, current, user, group, name="Notice watch"):
    conversation = await conversation_for(session, user, name)
    spec = build_spec(name=name)
    draft = await drafts.save_spec(session, current, conversation_id=conversation.id, spec=spec)
    draft = await drafts.save_settings(session, current, draft_id=draft.id,
        revision=draft.settings_revision, settings=build_settings(group.id))
    await collect(session, user, draft, collection_result(spec))
    monitor = await publish_draft(session, conversation, draft, current)
    await session.commit()
    return monitor, conversation, draft


async def add_snapshot(session, monitor, minute: int, state: str) -> Snapshot:
    job = Job(user_id=monitor.user_id, kind="production", status="succeeded",
              monitor_id=monitor.id, revision=monitor.spec_version)
    session.add(job)
    await session.flush()
    snapshot = Snapshot(monitor_id=monitor.id, job_id=job.id,
        spec_version=monitor.spec_version, final_url=monitor.url,
        extracted_data=extracted(state=state), coverage=COVERAGE,
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
    older = await add_snapshot(session, monitor, 1, "Open")
    newer = await add_snapshot(session, monitor, 2, "Closed")
    await session.commit()

    page = await monitors.list_snapshots(session, current, monitor.id, 10, 0)
    assert [row.id for row in page.items] == [newer.id, older.id]
    assert page.total == 2

    detail = await monitors.read_snapshot(session, current, older.id)
    assert detail.monitor_id == monitor.id
    assert detail.monitor_name == monitor.name
    assert detail.extracted_data["notice"][0]["state"] == "Open"

    stranger = User(email=f"{uuid4().hex}@example.com", display_name="Other",
                    password_hash="x", role="member")
    session.add(stranger)
    await session.flush()
    with pytest.raises(DomainError) as denied:
        await monitors.read_snapshot(session, CurrentUser(user_id=stranger.id, role="member"),
                                     older.id)
    # A member cannot distinguish a foreign row from a missing one.
    assert denied.value.code == "not_found"


@pytest.mark.asyncio
async def test_definition_versions_number_published_drafts(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    monitor, _, _ = await publish(session, current, user, group)

    conversation, draft = await drafts.draft_from_monitor(session, current, monitor.id)
    spec = build_spec(name="Notice watch", url="https://8.8.8.8/notice?v=2")
    draft = await drafts.save_spec(session, current, conversation_id=conversation.id,
                                  spec=spec, draft_id=draft.id)
    await collect(session, user, draft, collection_result(spec))
    await publish_draft(session, conversation, draft, current)
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
    assert renamed.spec_hash == content_hash(MonitorSpec.model_validate(renamed.spec))


@pytest.mark.asyncio
async def test_archive_pauses_and_cancels_but_keeps_history(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    monitor, _, _ = await publish(session, current, user, group)
    snapshot = await add_snapshot(session, monitor, 1, "Open")
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
