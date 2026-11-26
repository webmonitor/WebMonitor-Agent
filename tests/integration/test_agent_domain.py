"""Approval, account-activity and production-trigger regressions."""
import threading

import pytest
from sqlalchemy import func, select
from support import (
    build_settings,
    build_spec,
    collect,
    collection_result,
    prepare_draft,
    publish,
    seed_owner,
)
from test_runs import make_monitor, result, running_job

from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.models import Job, Monitor
from webmonitor.schemas.api import EmailTemplateSpec
from webmonitor.schemas.templates import EmailTemplateConfig
from webmonitor.services import drafts, jobs, monitors, runs, templates


async def _draft_with_template(session):
    user, current, group = await seed_owner(session)
    config = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name} 公告提醒",
        "blocks": [{"type": "field", "field": "page_title", "emphasis": True}],
    })
    template = await templates.write_template(session, current, EmailTemplateSpec(
        name="Approval design", description="", config=config))
    conversation, draft, _ = await prepare_draft(
        session, user, group, settings=build_settings(group.id, template_id=template.id))
    await session.commit()
    return conversation, draft, current, template, config


@pytest.mark.asyncio
async def test_publish_reads_template_once_and_freezes_the_validated_config(session, monkeypatch):
    conversation, draft, current, template, config = await _draft_with_template(session)
    original = templates.get_template
    reads = 0

    async def counted(session_, template_id, **kwargs):
        nonlocal reads
        if template_id == template.id:
            reads += 1
        return await original(session_, template_id, **kwargs)

    monkeypatch.setattr(templates, "get_template", counted)
    monitor = await publish(session, conversation, draft, current)

    assert reads == 1
    assert monitor.email_template is not None
    assert monitor.email_template["id"] == str(template.id)
    assert monitor.email_template["config"] == config.model_dump(mode="json")
    assert monitor.email_template["config"]["subject"] == "{monitor_name} 公告提醒"


@pytest.mark.asyncio
async def test_concurrent_template_change_before_approval_is_preview_stale(session):
    conversation, draft, current, template, config = await _draft_with_template(session)
    changed = config.model_copy(update={"subject": "{monitor_name} 新设计"})
    async with get_session_factory()() as concurrent:
        await templates.write_template(concurrent, current, EmailTemplateSpec(
            name=template.name, description=template.description, config=changed),
            template_id=template.id)
        await concurrent.commit()

    with pytest.raises(DomainError) as stale:
        await publish(session, conversation, draft, current)
    assert stale.value.code == "preview_stale"
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 0


@pytest.mark.asyncio
async def test_inactive_owner_cannot_resume_or_create_active_monitor(session):
    user, current, group = await seed_owner(session)
    monitor = await make_monitor(session, user, group)
    await monitors.pause_monitor(session, current, monitor.id)
    user.active = False
    await session.commit()

    with pytest.raises(DomainError) as inactive_resume:
        await monitors.resume_monitor(session, current, monitor.id)
    assert inactive_resume.value.code == "account_inactive"
    assert monitor.status == "paused"
    assert await session.scalar(select(func.count()).select_from(Job)) == 0

    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    with pytest.raises(DomainError) as inactive_publish:
        await publish(session, conversation, draft, current)
    assert inactive_publish.value.code == "account_inactive"
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1
    assert await session.scalar(select(func.count()).select_from(Monitor).where(
        Monitor.draft_id == draft.id)) == 0


@pytest.mark.asyncio
async def test_resume_reads_owner_before_locking_user_then_monitor(session, monkeypatch):
    user, current, group = await seed_owner(session)
    monitor = await make_monitor(session, user, group)
    await monitors.pause_monitor(session, current, monitor.id)
    await session.commit()
    calls = []
    original_read = monitors.read_monitor_row
    original_scalar = session.scalar

    async def recording_read(session_, user_, monitor_id, *, lock=False):
        calls.append("monitor_lock" if lock else "monitor_read")
        return await original_read(session_, user_, monitor_id, lock=lock)

    async def recording_scalar(_, statement, *args, **kwargs):
        sql = str(statement)
        if "FROM users" in sql and "FOR UPDATE" in sql:
            calls.append("user_lock")
        return await original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(monitors, "read_monitor_row", recording_read)
    monkeypatch.setattr(type(session), "scalar", recording_scalar)
    await monitors.resume_monitor(session, current, monitor.id)

    assert calls[:3] == ["monitor_read", "user_lock", "monitor_lock"]
    assert monitor.status == "active"


@pytest.mark.asyncio
async def test_republish_locks_user_monitor_then_job(session, monkeypatch):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    monitor = await publish(session, conversation, draft, current)
    in_flight = await jobs.enqueue(
        session, user_id=user.id, kind="production", monitor_id=monitor.id,
        revision=monitor.spec_version, url=monitor.url, spec=monitor.spec,
        source="scheduled")
    edit_conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    changed = build_spec(url="https://8.8.8.8/notice?page=2")
    await drafts.save_spec(
        session, current, conversation_id=edit_conversation.id, spec=changed, draft_id=edit.id)
    await collect(session, user, edit, collection_result(changed))
    await session.commit()

    calls = []
    original_scalar = session.scalar
    original_scalars = session.scalars
    original_get = session.get

    async def recording_scalar(_, statement, *args, **kwargs):
        sql = str(statement)
        if "FROM users" in sql and "FOR UPDATE" in sql:
            calls.append("user_lock")
        return await original_scalar(statement, *args, **kwargs)

    async def recording_scalars(_, statement, *args, **kwargs):
        sql = str(statement)
        if "FROM jobs" in sql and "FOR UPDATE" in sql:
            calls.append("job_lock")
        return await original_scalars(statement, *args, **kwargs)

    async def recording_get(_, entity, ident, **kwargs):
        if entity is Monitor and kwargs.get("with_for_update"):
            calls.append("monitor_lock")
        return await original_get(entity, ident, **kwargs)

    monkeypatch.setattr(type(session), "scalar", recording_scalar)
    monkeypatch.setattr(type(session), "scalars", recording_scalars)
    monkeypatch.setattr(type(session), "get", recording_get)
    await publish(session, edit_conversation, edit, current)

    assert calls.index("user_lock") < calls.index("monitor_lock") < calls.index("job_lock")
    assert in_flight.status == "cancelled"


@pytest.mark.asyncio
async def test_scheduled_jobs_do_not_consume_manual_quota(session, monkeypatch):
    user, current, group = await seed_owner(session)
    monitor = await make_monitor(session, user, group)
    configured = get_settings().model_copy(update={"manual_runs_per_hour": 1})
    monkeypatch.setattr(monitors, "get_settings", lambda: configured)

    assert await runs.schedule_due(session) == 1
    scheduled = await session.scalar(select(Job).where(Job.monitor_id == monitor.id))
    assert scheduled is not None and scheduled.source == "scheduled"
    await jobs.finish(session, scheduled, "succeeded")
    await session.commit()

    manual = await monitors.enqueue_manual(session, current, monitor.id)
    assert manual.source == "manual"
    await jobs.finish(session, manual, "succeeded")
    await session.commit()

    with pytest.raises(DomainError) as limited:
        await monitors.enqueue_manual(session, current, monitor.id)
    assert limited.value.code == "rate_limited"
    assert await session.scalar(select(func.count()).select_from(Job).where(
        Job.kind == "production", Job.source == "manual")) == 1


@pytest.mark.asyncio
async def test_preview_rule_evaluation_runs_off_the_event_loop(session, monkeypatch):
    user, _, group = await seed_owner(session)
    original = drafts.evaluate_rules
    threads = []

    def evaluated(*args):
        threads.append(threading.get_ident())
        return original(*args)

    monkeypatch.setattr(drafts, "evaluate_rules", evaluated)
    await prepare_draft(session, user, group)

    assert threads
    assert all(thread != threading.get_ident() for thread in threads)


@pytest.mark.asyncio
async def test_production_rule_evaluation_runs_off_the_event_loop(session, monkeypatch):
    user, _, group = await seed_owner(session)
    monitor = await make_monitor(session, user, group)
    job = await running_job(session, monitor)
    original = runs.evaluate_rules
    threads = []

    def evaluated(*args):
        threads.append(threading.get_ident())
        return original(*args)

    monkeypatch.setattr(runs, "evaluate_rules", evaluated)
    assert await runs.commit_success(session, job, result("A")) is True

    assert threads
    assert all(thread != threading.get_ident() for thread in threads)
