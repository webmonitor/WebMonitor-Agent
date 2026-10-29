"""One draft publishes exactly one monitor, and a repeated approval is idempotent."""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from webmonitor.errors import DomainError
from webmonitor.models import Draft, Monitor, NotificationGroup, User
from webmonitor.schemas.monitors import DraftSpec, content_hash
from webmonitor.security.auth import CurrentUser
from webmonitor.services import drafts
from webmonitor.services.notifications import load_recipients, recipients_emails


def build_spec(group_id) -> DraftSpec:
    return DraftSpec.model_validate({
        "name": "Price watch",
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


def preview_payload(spec: DraftSpec, draft: Draft, recipients: list[str], price: str) -> dict:
    return {
        "revision": draft.revision,
        "spec_hash": content_hash(spec),
        "extracted_data": {"current_price": {"amount": price, "currency": "USD"}},
        "coverage": {"scope": "full", "description": "Single price element"},
        "final_url": spec.url,
        "evidence_refs": [],
        "rule_simulation": {"triggered": False},
        "rendered_emails": [],
        "recipients": recipients,
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_publish_creates_one_monitor_and_repeats_idempotently(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await _conversation(session, user)
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id,
                                    spec=build_spec(group.id))
    assert draft.revision == 1

    spec = DraftSpec.model_validate(draft.spec)
    recipients = recipients_emails(await load_recipients(session, spec.notification_group_ids))
    assert recipients == ["ops@example.com"]
    await drafts.save_preview(session, draft,
        preview_payload(spec, draft, recipients, "100"), ttl_minutes=60)
    await session.commit()

    monitor = await drafts.publish_draft(session, current,
        conversation_id=conversation.id, draft_id=draft.id, revision=draft.revision)
    await session.commit()

    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1
    assert monitor.draft_id == draft.id
    assert monitor.spec_version == 1
    assert monitor.baseline_status == "pending_first_success"
    assert monitor.collection_mode == "http"
    assert monitor.interval_seconds == 60
    assert monitor.notification_group_ids == [str(group.id)]
    stored = await session.get(Draft, draft.id)
    assert stored.status == "published"
    assert stored.monitor_id == monitor.id

    again = await drafts.publish_draft(session, current,
        conversation_id=conversation.id, draft_id=draft.id, revision=draft.revision)
    await session.commit()
    assert again.id == monitor.id
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1


@pytest.mark.asyncio
async def test_editing_the_spec_invalidates_the_previous_preview(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await _conversation(session, user)
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id,
                                    spec=build_spec(group.id))
    spec = DraftSpec.model_validate(draft.spec)
    recipients = recipients_emails(await load_recipients(session, spec.notification_group_ids))
    await drafts.save_preview(session, draft, preview_payload(spec, draft, recipients, "100"),
                              ttl_minutes=60)
    await session.commit()

    edited = await drafts.save_draft(session, current, conversation_id=conversation.id,
                                     spec=build_spec(group.id), draft_id=draft.id)
    await session.commit()
    assert edited.revision == 2
    assert edited.preview is None

    with pytest.raises(DomainError) as raised:
        await drafts.publish_draft(session, current, conversation_id=conversation.id,
                                   draft_id=draft.id, revision=2)
    assert raised.value.code == "preview_missing"

    with pytest.raises(DomainError) as stale:
        await drafts.publish_draft(session, current, conversation_id=conversation.id,
                                   draft_id=draft.id, revision=1)
    assert stale.value.code == "stale_revision"


@pytest.mark.asyncio
async def test_recipient_change_after_preview_blocks_publication(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await _conversation(session, user)
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id,
                                    spec=build_spec(group.id))
    spec = DraftSpec.model_validate(draft.spec)
    recipients = recipients_emails(await load_recipients(session, spec.notification_group_ids))
    await drafts.save_preview(session, draft, preview_payload(spec, draft, recipients, "100"),
                              ttl_minutes=60)
    await session.commit()

    group.members = [{"email": "other@example.com", "active": True}]
    await session.flush()

    with pytest.raises(DomainError) as raised:
        await drafts.publish_draft(session, current, conversation_id=conversation.id,
                                   draft_id=draft.id, revision=draft.revision)
    assert raised.value.code == "preview_stale"


@pytest.mark.asyncio
async def test_editing_a_published_draft_starts_a_new_baseline(session):
    user, group = await seed(session)
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = await _conversation(session, user)
    draft = await drafts.save_draft(session, current, conversation_id=conversation.id,
                                    spec=build_spec(group.id))
    spec = DraftSpec.model_validate(draft.spec)
    recipients = recipients_emails(await load_recipients(session, spec.notification_group_ids))
    await drafts.save_preview(session, draft, preview_payload(spec, draft, recipients, "100"),
                              ttl_minutes=60)
    await session.commit()
    monitor = await drafts.publish_draft(session, current, conversation_id=conversation.id,
                                         draft_id=draft.id, revision=draft.revision)
    monitor.baseline_status = "ready"
    monitor.rule_state = {"predicates": {"0": True}, "aggregate": True}
    monitor.baseline_snapshot_id = uuid4()
    monitor.health_status = "failed"
    await session.commit()

    # Editing the notification group derives a fresh draft bound to the same monitor.
    group.members = [{"email": "other@example.com", "active": True}]
    await session.flush()
    derived_conversation, derived = await drafts.draft_from_monitor(session, current, monitor.id)
    await session.commit()
    assert derived.monitor_id == monitor.id
    edited_spec = DraftSpec.model_validate(derived.spec)
    edited_recipients = recipients_emails(
        await load_recipients(session, edited_spec.notification_group_ids))
    await drafts.save_preview(session, derived,
        preview_payload(edited_spec, derived, edited_recipients, "100"), ttl_minutes=60)
    await session.commit()

    published = await drafts.publish_draft(session, current,
        conversation_id=derived_conversation.id, draft_id=derived.id,
        revision=derived.revision)
    await session.commit()

    assert published.id == monitor.id
    assert published.spec_version == 2
    # The previous contract's snapshot, rule indexes and health do not carry over.
    assert published.baseline_status == "pending_first_success"
    assert published.baseline_snapshot_id is None
    assert published.rule_state == {}
    assert published.health_status == "healthy"
    assert published.failure_fingerprint is None
    assert await session.scalar(select(func.count()).select_from(Monitor)) == 1


async def _conversation(session, user):
    from webmonitor.models import Conversation
    conversation = Conversation(user_id=user.id, title="Approval flow")
    session.add(conversation)
    await session.flush()
    return conversation
