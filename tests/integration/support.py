"""Shared builders: real drafts, real previews, no hand-written preview payloads."""
from datetime import timedelta
from typing import Any
from uuid import uuid4

from webmonitor.models import Conversation, Draft, Job, Monitor, NotificationGroup, User, utc_now
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.security.auth import CurrentUser
from webmonitor.services import drafts, jobs

NOTICE_SPEC = {
    "name": "Notice watch",
    "url": "https://8.8.8.8/notice",
    "collection_mode": "http",
    "fields": [
        {"name": "page_title", "type": "text", "semantic": "Page title", "selector": "h1"},
        {"name": "notice", "type": "list", "semantic": "Notices", "selector": "li",
         "item_fields": [
             {"name": "title", "type": "text", "semantic": "Title", "selector": ".t"},
             {"name": "state", "type": "text", "semantic": "State", "selector": ".s"}]},
    ],
    "business_key": {"field": "notice", "item_fields": ["title"]},
    "change_rules": {"mode": "any", "rules": [
        {"type": "text_changed", "field": "page_title"},
        {"type": "list_updated", "field": "notice", "watch_fields": ["state"]}]},
    "coverage": {"scope": "full", "description": "Whole notice list"},
}

COVERAGE = {"scope": "full", "description": "Whole notice list"}


def build_spec(name: str = "Notice watch", url: str = NOTICE_SPEC["url"]) -> MonitorSpec:
    return MonitorSpec.model_validate({**NOTICE_SPEC, "name": name, "url": url})


def build_settings(group_id, *, interval: int = 60, timezone: str = "UTC",
                   template_id=None) -> DeliverySettings:
    return DeliverySettings.model_validate({
        "notification_group_ids": [str(group_id)],
        "schedule": {"interval_seconds": interval, "timezone": timezone},
        "email_template_id": str(template_id) if template_id is not None else None,
    })


def extracted(title: str = "Semester notices", state: str = "Open") -> dict[str, Any]:
    return {"page_title": title, "notice": [{"title": "Registration", "state": state}]}


def collection_result(spec: MonitorSpec | None = None, title: str = "Semester notices",
                      state: str = "Open") -> dict[str, Any]:
    spec = spec or build_spec()
    return {"fields": extracted(title, state), "coverage": COVERAGE,
            "final_url": spec.url, "evidence_refs": [], "warnings": []}


async def seed_owner(session) -> tuple[User, CurrentUser, NotificationGroup]:
    user = User(email=f"{uuid4().hex}@example.com", display_name="Owner",
                password_hash="not-a-login-hash", role="admin")
    session.add(user)
    await session.flush()
    group = NotificationGroup(name=f"Ops {uuid4().hex}", members=[
        {"email": "ops@example.com", "active": True}], created_by_user_id=user.id)
    session.add(group)
    await session.flush()
    return user, CurrentUser(user_id=user.id, role="admin"), group


async def conversation_for(session, user: User, title: str = "Approval flow") -> Conversation:
    conversation = Conversation(user_id=user.id, title=title)
    session.add(conversation)
    await session.flush()
    return conversation


async def prepare_draft(session, user: User, group: NotificationGroup, *,
                        spec: MonitorSpec | None = None,
                        settings: DeliverySettings | None = None,
                        result: dict | None = None,
                        conversation: Conversation | None = None,
                        build_previews: bool = True) -> tuple[Conversation, Draft, CurrentUser]:
    """Save both sections, then run the real preview pipeline for a collected page."""
    current = CurrentUser(user_id=user.id, role="admin")
    conversation = conversation or await conversation_for(session, user)
    spec = spec or build_spec()
    settings = settings if settings is not None else build_settings(group.id)
    draft = await drafts.save_spec(session, current, conversation_id=conversation.id, spec=spec)
    draft = await drafts.save_settings(session, current, draft_id=draft.id,
                                       revision=draft.settings_revision, settings=settings)
    if build_previews:
        await collect(session, user, draft, result or collection_result(spec))
    return conversation, draft, current


async def collect(session, user: User, draft: Draft, result: dict) -> dict:
    """Persist a finished preview job and let the worker code freeze the previews."""
    job = Job(user_id=user.id, kind="preview", status="running", draft_id=draft.id,
              revision=draft.spec_revision, url=(draft.spec or {}).get("url"),
              lease_owner="worker", spec=draft.spec, attempt_count=1,
              lease_expires_at=utc_now() + timedelta(seconds=90), result=result)
    session.add(job)
    await session.flush()
    await drafts.build_preview(session, draft, job)
    # The worker marks the job terminal after freezing the preview.
    await jobs.finish(session, job, "succeeded", result=result)
    await session.flush()
    return draft.extraction_preview or {}


async def publish(session, conversation: Conversation, draft: Draft, current: CurrentUser) -> Monitor:
    return await drafts.publish_draft(session, current, conversation_id=conversation.id,
        draft_id=draft.id, spec_revision=draft.spec_revision,
        settings_revision=draft.settings_revision,
        extraction_preview_hash=draft.extraction_preview_hash or "0" * 64,
        delivery_preview_hash=draft.delivery_preview_hash or "0" * 64)
