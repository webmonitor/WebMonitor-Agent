"""One draft publishes exactly one monitor; settings and contract publish separately."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from support import (
    build_settings,
    build_spec,
    collect,
    collection_result,
    conversation_for,
    prepare_draft,
    publish,
    seed_owner,
)

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Draft, Monitor, NotificationGroup, User
from webmonitor.schemas.api import DraftUpdate, EmailTemplateSpec
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.schemas.templates import EmailTemplateConfig
from webmonitor.security.auth import CurrentUser
from webmonitor.services import drafts, jobs, templates
from webmonitor.services.monitors import list_spec_versions


@pytest.mark.asyncio
async def test_publish_creates_one_monitor_and_repeats_idempotently(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    assert draft.spec_revision == 1 and draft.settings_revision == 1
    assert draft.extraction_preview is not None and draft.delivery_preview is not None
    await session.commit()

    monitor = await publish(session, conversation, draft, current)
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1
    assert monitor.draft_id == draft.id
    assert monitor.spec_version == 1
    assert monitor.baseline_status == "pending_first_success"
    assert monitor.collection_mode == "http"
    assert monitor.interval_seconds == 60
    assert monitor.notification_group_ids == [str(group.id)]
    assert monitor.email_template_id is None and monitor.email_template is None
    assert "schedule" not in monitor.spec and "notification_group_ids" not in monitor.spec
    stored = await session.get(Draft, draft.id)
    assert stored.status == "published"
    assert stored.monitor_id == monitor.id
    assert stored.published_spec_version == 1

    again = await publish(session, conversation, draft, current)
    await session.commit()
    assert again.id == monitor.id
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1


@pytest.mark.asyncio
async def test_preview_seeds_delivery_defaults_and_publishes_without_user_settings(session):
    """Delivery is the operator's, not the conversation's: a preview seeds it."""
    user, current, group = await seed_owner(session)
    conversation = await conversation_for(session, user)
    spec = build_spec()
    draft = await drafts.save_spec(session, current, conversation_id=conversation.id, spec=spec)
    assert draft.settings_revision == 0 and not draft.settings

    queued = await drafts.start_preview(session, current, draft.id)
    await session.commit()

    seeded = DeliverySettings.model_validate(draft.settings)
    assert draft.settings_revision == 1
    assert seeded.schedule is not None
    assert seeded.schedule.interval_seconds == get_settings().default_interval_seconds
    assert [str(item) for item in seeded.notification_group_ids] == [str(group.id)]

    # The worker that would have run this job writes the previews instead.
    await jobs.finish(session, queued, "cancelled")
    await collect(session, user, draft, collection_result(spec))
    await session.commit()
    # The settings the preview rendered are the ones publication applies.
    await drafts.validate_delivery_preview(session, draft)
    monitor = await publish(session, conversation, draft, current)
    await session.commit()

    assert monitor.interval_seconds == get_settings().default_interval_seconds
    assert monitor.notification_group_ids == [str(group.id)]


@pytest.mark.asyncio
async def test_a_group_created_after_the_first_preview_is_seeded_by_a_rerun(session):
    """Without a group the first preview has no recipient; a rerun must pick one up."""
    user = User(email=f"{uuid4().hex}@example.com", display_name="Owner",
                password_hash="not-a-login-hash", role="admin")
    session.add(user)
    await session.flush()
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await conversation_for(session, user)
    spec = build_spec()
    draft = await drafts.save_spec(session, current, conversation_id=conversation.id, spec=spec)

    first = await drafts.start_preview(session, current, draft.id)
    await jobs.finish(session, first, "cancelled")
    await collect(session, user, draft, collection_result(spec))
    assert draft.delivery_preview is None
    assert DeliverySettings.model_validate(draft.settings).notification_group_ids == []

    group = NotificationGroup(name=f"Ops {uuid4().hex}", members=[
        {"email": "ops@example.com", "active": True}], created_by_user_id=user.id)
    session.add(group)
    await session.flush()

    second = await drafts.start_preview(session, current, draft.id)
    await jobs.finish(session, second, "cancelled")
    await collect(session, user, draft, collection_result(spec))
    await session.commit()

    assert [str(item) for item in DeliverySettings.model_validate(
        draft.settings).notification_group_ids] == [str(group.id)]
    assert draft.delivery_preview is not None
    assert draft.delivery_preview["settings_revision"] == draft.settings_revision
    await drafts.validate_delivery_preview(session, draft)
    monitor = await publish(session, conversation, draft, current)
    await session.commit()
    assert monitor.notification_group_ids == [str(group.id)]


@pytest.mark.asyncio
async def test_changing_only_the_schedule_keeps_the_extraction_preview(session):
    user, current, group = await seed_owner(session)
    _, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    extraction_hash = draft.extraction_preview_hash
    delivery_hash = draft.delivery_preview_hash

    await drafts.save_settings(session, current, draft_id=draft.id,
        revision=draft.settings_revision,
        settings=build_settings(group.id, interval=600))
    await session.commit()

    assert draft.settings_revision == 2 and draft.spec_revision == 1
    assert draft.extraction_preview_hash == extraction_hash
    assert draft.delivery_preview_hash is not None
    assert draft.delivery_preview_hash != delivery_hash
    # The rebuilt mail still matches the current settings revision.
    delivery = await drafts.validate_delivery_preview(session, draft)
    assert delivery["settings_revision"] == 2


@pytest.mark.asyncio
async def test_changing_the_spec_clears_both_previews(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()

    await drafts.save_spec(session, current, conversation_id=conversation.id,
                           spec=build_spec(name="Price watch v2"), draft_id=draft.id)
    await session.commit()

    assert draft.spec_revision == 2
    assert draft.extraction_preview is None and draft.delivery_preview is None
    assert draft.extraction_preview_hash is None and draft.delivery_preview_hash is None
    with pytest.raises(DomainError) as missing:
        drafts.validate_extraction_preview(draft)
    assert missing.value.code == "preview_missing"


@pytest.mark.asyncio
async def test_settings_only_publish_of_a_derived_draft_keeps_the_baseline(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    monitor = await publish(session, conversation, draft, current)
    monitor.baseline_snapshot_id = uuid4()
    monitor.baseline_status = "ready"
    monitor.rule_state = {"predicates": {"0": True}, "aggregate": True}
    monitor.health_status = "failed"
    monitor.failure_fingerprint = "f" * 64
    baseline_id, rule_state = monitor.baseline_snapshot_id, dict(monitor.rule_state)
    await session.commit()

    edit_conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    edit = await drafts.save_settings(session, current, draft_id=edit.id,
        revision=edit.settings_revision,
        settings=build_settings(group.id, interval=900, timezone="Asia/Shanghai"))
    await collect_after_settings(session, user, edit)
    await session.commit()

    published = await publish(session, edit_conversation, edit, current)
    await session.commit()

    assert published.id == monitor.id
    assert published.spec_version == 1
    assert published.baseline_snapshot_id == baseline_id
    assert published.baseline_status == "ready"
    assert published.rule_state == rule_state
    assert published.health_status == "failed"
    assert published.failure_fingerprint == "f" * 64
    assert published.interval_seconds == 900
    assert published.timezone == "Asia/Shanghai"
    stored = await session.get(Draft, edit.id)
    assert stored.published_spec_version is None
    versions = await list_spec_versions(session, current, monitor.id, 10, 0)
    assert [item.version for item in versions.items] == [1]
    assert all(item.current for item in versions.items)


@pytest.mark.asyncio
async def test_contract_change_publish_increments_version_and_resets_the_baseline(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    monitor = await publish(session, conversation, draft, current)
    monitor.baseline_snapshot_id = uuid4()
    monitor.baseline_status = "ready"
    monitor.rule_state = {"predicates": {"0": True}, "aggregate": True}
    monitor.health_status = "failed"
    monitor.failure_fingerprint = "f" * 64
    await session.commit()

    edit_conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    edit = await drafts.save_spec(session, current, conversation_id=edit.conversation_id,
        spec=build_spec(url="https://8.8.8.8/product?page=2"), draft_id=edit.id)
    await collect_after_settings(session, user, edit)
    await session.commit()

    published = await publish(session, edit_conversation, edit, current)
    await session.commit()

    assert published.id == monitor.id
    assert published.spec_version == 2
    assert published.baseline_status == "pending_first_success"
    assert published.baseline_snapshot_id is None
    assert published.rule_state == {}
    assert published.health_status == "healthy"
    assert published.failure_fingerprint is None
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1
    versions = await list_spec_versions(session, current, monitor.id, 10, 0)
    assert [(item.version, item.current) for item in versions.items] == [(2, True), (1, False)]


@pytest.mark.asyncio
async def test_renaming_only_does_not_reset_the_baseline(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    monitor = await publish(session, conversation, draft, current)
    monitor.baseline_status = "ready"
    monitor.baseline_snapshot_id = uuid4()
    await session.commit()

    edit_conversation, edit = await drafts.draft_from_monitor(session, current, monitor.id)
    edit = await drafts.save_spec(session, current, conversation_id=edit.conversation_id,
                                  spec=build_spec(name="Renamed watch"), draft_id=edit.id)
    await collect_after_settings(session, user, edit)
    await session.commit()

    published = await publish(session, edit_conversation, edit, current)
    await session.commit()
    assert published.name == "Renamed watch"
    assert published.spec["name"] == "Renamed watch"
    assert published.spec_version == 1
    assert published.baseline_status == "ready"


@pytest.mark.asyncio
async def test_recipient_change_after_preview_blocks_publication(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()

    group.members = [{"email": "other@example.com", "active": True}]
    await session.flush()

    with pytest.raises(DomainError) as raised:
        await publish(session, conversation, draft, current)
    assert raised.value.code == "preview_stale"


@pytest.mark.asyncio
async def test_publication_requires_groups_and_a_schedule(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await drafts.save_settings(session, current, draft_id=draft.id,
        revision=draft.settings_revision, settings=build_settings(group.id))
    draft.settings = {}
    draft.settings_hash = None
    await session.flush()
    await session.commit()

    with pytest.raises(DomainError) as raised:
        await publish(session, conversation, draft, current)
    assert raised.value.code == "settings_incomplete"
    assert raised.value.details["missing"] == ["notification_group_ids", "schedule"]


@pytest.mark.asyncio
async def test_direct_edit_replaces_the_spec_and_invalidates_the_preview(session):
    user, current, group = await seed_owner(session)
    _, draft, _ = await prepare_draft(session, user, group)
    await session.commit()

    updated = await drafts.apply_update(session, current, draft.id, DraftUpdate(
        spec_revision=draft.spec_revision, spec=build_spec(name="Price watch v2")))
    await session.commit()

    assert updated.id == draft.id
    assert updated.spec_revision == 2
    assert updated.settings_revision == 1
    assert updated.spec["name"] == "Price watch v2"
    assert updated.extraction_preview is None and updated.extraction_preview_hash is None
    assert updated.delivery_preview is None

    with pytest.raises(DomainError) as stale:
        await drafts.apply_update(session, current, draft.id, DraftUpdate(
            spec_revision=1, spec=build_spec(name="Price watch v2")))
    assert stale.value.code == "stale_revision"


@pytest.mark.asyncio
async def test_direct_settings_edit_leaves_the_extraction_preview_intact(session):
    user, current, group = await seed_owner(session)
    _, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    extraction_hash = draft.extraction_preview_hash

    updated = await drafts.apply_update(session, current, draft.id, DraftUpdate(
        settings_revision=draft.settings_revision,
        settings=build_settings(group.id, interval=3600)))
    await session.commit()
    assert updated.settings_revision == 2 and updated.spec_revision == 1
    assert updated.extraction_preview_hash == extraction_hash

    with pytest.raises(DomainError) as stale:
        await drafts.apply_update(session, current, draft.id, DraftUpdate(
            settings_revision=1, settings=build_settings(group.id)))
    assert stale.value.code == "stale_revision"


@pytest.mark.asyncio
async def test_published_draft_cannot_be_edited_directly(session):
    user, current, group = await seed_owner(session)
    conversation, draft, _ = await prepare_draft(session, user, group)
    await session.commit()
    await publish(session, conversation, draft, current)
    await session.commit()

    with pytest.raises(DomainError) as rejected:
        await drafts.apply_update(session, current, draft.id, DraftUpdate(
            spec_revision=draft.spec_revision, spec=build_spec()))
    assert rejected.value.code == "draft_not_editable"


@pytest.mark.asyncio
async def test_template_snapshot_survives_template_deletion(session):
    user, current, group = await seed_owner(session)
    config = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name} 公告提醒",
        "blocks": [{"type": "field", "field": "page_title", "emphasis": True}]})
    template = await templates.write_template(session, current, _template_spec(config))
    conversation, draft, _ = await prepare_draft(session, user, group,
        settings=build_settings(group.id, template_id=template.id))
    await session.commit()
    monitor = await publish(session, conversation, draft, current)
    await session.commit()
    assert monitor.email_template is not None
    snapshot = dict(monitor.email_template)
    assert snapshot["name"] == template.name
    assert snapshot["config"]["subject"] == "{monitor_name} 公告提醒"

    await templates.disable_template(session, current, template.id)
    await session.commit()
    stored = await session.get(Monitor, monitor.id)
    assert stored.email_template == snapshot
    assert stored.email_template["name"] == template.name


@pytest.mark.asyncio
async def test_draft_referencing_a_deleted_template_cannot_publish(session):
    user, current, group = await seed_owner(session)
    config = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name}", "blocks": [{"type": "summary"}]})
    template = await templates.write_template(session, current, _template_spec(config))
    conversation, draft, _ = await prepare_draft(session, user, group,
        settings=build_settings(group.id, template_id=template.id))
    await session.commit()

    await templates.disable_template(session, current, template.id)
    await session.commit()

    with pytest.raises(DomainError) as unavailable:
        await publish(session, conversation, draft, current)
    assert unavailable.value.code == "template_unavailable"


@pytest.mark.asyncio
async def test_incompatible_template_is_rejected_when_settings_are_saved(session):
    user, current, group = await seed_owner(session)
    config = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name}",
        "blocks": [{"type": "field", "field": "missing_field"}]})
    template = await templates.write_template(session, current, _template_spec(config))
    conversation = await conversation_for(session, user)
    draft = await drafts.save_spec(session, current, conversation_id=conversation.id,
                                   spec=build_spec())

    with pytest.raises(DomainError) as raised:
        await drafts.save_settings(session, current, draft_id=draft.id,
            revision=draft.settings_revision,
            settings=build_settings(group.id, template_id=template.id))
    assert raised.value.code == "template_incompatible"
    assert raised.value.details["fields"] == ["missing_field"]


async def collect_after_settings(session, user, draft):
    """A derived or edited draft has no preview yet; run the real pipeline for it."""
    return await collect(session, user, draft,
                         collection_result(MonitorSpec.model_validate(draft.spec)))


def _template_spec(config: EmailTemplateConfig) -> EmailTemplateSpec:
    return EmailTemplateSpec(name=f"Design {uuid4().hex[:8]}", description="", config=config)


@pytest.mark.asyncio
async def test_webhook_settings_publish_a_json_preview_without_groups(session):
    user, current, group = await seed_owner(session)
    settings = DeliverySettings.model_validate({
        "channel": "webhook",
        "webhook_url": "https://hooks.example.com/ops",
        "schedule": {"interval_seconds": 120, "timezone": "UTC"},
    })
    conversation, draft, _ = await prepare_draft(session, user, group, settings=settings)
    await session.commit()

    preview = draft.delivery_preview or {}
    assert preview["channel"] == "webhook"
    assert preview["webhook_url"] == "https://hooks.example.com/ops"
    assert preview["rendered_emails"] == []
    assert preview["recipients"] == []
    assert preview["webhook_body"]["monitor"]["name"] == "Notice watch"

    monitor = await publish(session, conversation, draft, current)
    await session.commit()
    assert monitor.delivery_channel == "webhook"
    assert monitor.webhook_url == "https://hooks.example.com/ops"
    assert monitor.approved_recipients == []
    assert monitor.interval_seconds == 120
