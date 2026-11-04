"""Two independently versioned draft sections and the single publication path.

The collection contract (`MonitorSpec`) and the user's delivery settings
(`DeliverySettings`) carry their own revision, hash and preview. Editing one never
invalidates the other's preview, and the agent can only write the collection contract.
"""
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.collection.diff import evaluate_rules
from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Draft, Job, Monitor, User, utc_now
from webmonitor.notifications.rendering import render_email, sanitize_preview
from webmonitor.schemas.api import (
    CreateMonitorResult,
    DeliveryPreview,
    DraftUpdate,
    ExtractionPreview,
)
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.schemas.monitors import MonitorSpec, Schedule, content_hash
from webmonitor.schemas.templates import (
    EmailTemplateConfig,
    TemplateIncompatible,
    validate_template_for_spec,
)
from webmonitor.security.auth import CurrentUser, require_owner
from webmonitor.security.egress import validate_url
from webmonitor.services import jobs, notifications, templates

EXTRACTION_KEYS = ("preview_id", "spec_revision", "spec_hash", "extracted_data", "coverage",
                   "final_url", "evidence_refs", "rule_simulation", "source", "warnings")
DELIVERY_KEYS = ("preview_id", "settings_revision", "settings_hash", "template_id",
                 "template_name", "template_hash", "rendered_emails", "recipients",
                 "recipient_sources", "warnings")
# A delivery preview that cannot be rendered never invalidates a real collection.
DELIVERY_WARNINGS = frozenset({"notification_routes_invalid", "notification_recipients_empty",
                               "template_unavailable", "template_incompatible",
                               "template_contract_failed"})


async def require_draft(session: AsyncSession, user: CurrentUser, draft_id: UUID,
                        *, lock: bool = False) -> Draft:
    query = select(Draft).where(Draft.id == draft_id)
    if lock:
        query = query.with_for_update()
    return require_owner(user, await session.scalar(
        query.execution_options(populate_existing=True)))


def _spec(draft: Draft) -> MonitorSpec:
    if draft.spec is None:
        raise DomainError("draft_empty", 409)
    return MonitorSpec.model_validate(draft.spec)


def _settings(draft: Draft) -> DeliverySettings:
    return DeliverySettings.model_validate(draft.settings or {})


def _clear_extraction_preview(draft: Draft) -> None:
    draft.extraction_preview = None
    draft.extraction_preview_hash = None
    draft.extraction_preview_expires_at = None


def _clear_delivery_preview(draft: Draft) -> None:
    draft.delivery_preview = None
    draft.delivery_preview_hash = None
    draft.delivery_preview_expires_at = None


def _event_types(spec: MonitorSpec) -> set[str]:
    """Which mail an approved monitor can send: one per kind of change it watches."""
    types = {"run_failed", "recovered"}
    fields = {field.name: field for field in spec.fields}
    for rule in spec.change_rules.rules:
        types.add("list_changed" if fields[rule.field].type == "list"
                  else "content_changed")
    return types


def extraction_hash(payload: dict) -> str:
    return content_hash({key: payload.get(key) for key in EXTRACTION_KEYS})


def delivery_hash(payload: dict) -> str:
    return content_hash({key: payload.get(key) for key in DELIVERY_KEYS})


# ---- writing each section ---------------------------------------------------

async def _open_draft(session: AsyncSession, user: CurrentUser, *, conversation_id: UUID,
                      draft_id: UUID | None) -> Draft:
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id).with_for_update()
        .execution_options(populate_existing=True))
    require_owner(user, conversation)
    if draft_id is None:
        draft = Draft(user_id=user.user_id, conversation_id=conversation.id, status="draft")
        session.add(draft)
        await session.flush()
        return draft
    draft = await require_draft(session, user, draft_id, lock=True)
    if draft.conversation_id != conversation.id:
        raise DomainError("not_found", 404)
    if draft.status != "draft":
        raise DomainError("draft_not_editable", 409)
    return draft


async def save_spec(session: AsyncSession, user: CurrentUser, *, conversation_id: UUID,
                    spec: MonitorSpec, draft_id: UUID | None = None,
                    expected_revision: int | None = None) -> Draft:
    """Replace the collection contract; delivery settings are never touched."""
    spec = MonitorSpec.model_validate(spec)
    draft = await _open_draft(session, user, conversation_id=conversation_id, draft_id=draft_id)
    if expected_revision is not None and expected_revision != draft.spec_revision:
        raise DomainError("stale_revision", 409)
    draft.spec_revision += 1
    draft.spec = spec.model_dump(mode="json")
    draft.spec_hash = content_hash(spec)
    # A changed collection contract invalidates both previews of this draft.
    _clear_extraction_preview(draft)
    _clear_delivery_preview(draft)
    draft.status = "draft"
    draft.updated_at = utc_now()
    await jobs.cancel_pending(session, draft_id=draft.id)
    await session.flush()
    return draft


async def _validate_settings(session: AsyncSession, draft: Draft,
                             settings: DeliverySettings) -> None:
    if settings.notification_group_ids:
        await notifications.load_recipients(session, settings.notification_group_ids)
    if settings.email_template_id is None or draft.spec is None:
        return
    await _resolve_template(session, settings.email_template_id, _spec(draft))


async def save_settings(session: AsyncSession, user: CurrentUser, *, draft_id: UUID,
                        revision: int, settings: DeliverySettings) -> Draft:
    """Replace the delivery settings; a valid extraction preview survives.

    A rebuild of the mail preview needs the collected data, so it happens here when a
    current extraction preview exists and nothing else is in flight.
    """
    draft = await require_draft(session, user, draft_id, lock=True)
    if draft.status != "draft":
        raise DomainError("draft_not_editable", 409)
    if draft.settings_revision != revision:
        raise DomainError("stale_revision", 409)
    settings = DeliverySettings.model_validate(settings)
    await _validate_settings(session, draft, settings)
    draft.settings_revision += 1
    draft.settings = settings.model_dump(mode="json")
    draft.settings_hash = content_hash(settings)
    _clear_delivery_preview(draft)
    draft.updated_at = utc_now()
    if draft.extraction_preview is not None:
        await build_delivery_preview(session, draft)
    await session.flush()
    return draft


async def apply_update(session: AsyncSession, user: CurrentUser, draft_id: UUID,
                       payload: DraftUpdate) -> Draft:
    """Apply the sections the caller supplied, each behind its own revision."""
    draft = await require_draft(session, user, draft_id, lock=True)
    if draft.status != "draft":
        raise DomainError("draft_not_editable", 409)
    if payload.spec is not None:
        if payload.spec_revision != draft.spec_revision:
            raise DomainError("stale_revision", 409)
        draft = await save_spec(session, user, conversation_id=draft.conversation_id,
                                spec=payload.spec, draft_id=draft.id)
    if payload.settings is not None:
        if payload.settings_revision != draft.settings_revision:
            raise DomainError("stale_revision", 409)
        draft = await save_settings(session, user, draft_id=draft.id,
                                    revision=payload.settings_revision,
                                    settings=payload.settings)
    return draft


async def draft_from_monitor(session: AsyncSession, user: CurrentUser,
                             monitor_id: UUID) -> tuple[Conversation, Draft]:
    """Seed a draft with the monitor's current contract and settings, without a preview."""
    monitor = require_owner(user, await session.get(Monitor, monitor_id))
    conversation = Conversation(user_id=user.user_id,
        title=f"修改监控：{monitor.name}"[:200])
    session.add(conversation)
    await session.flush()
    settings = DeliverySettings(
        notification_group_ids=[UUID(item) for item in monitor.notification_group_ids or []],
        schedule={"interval_seconds": monitor.interval_seconds, "timezone": monitor.timezone},
        email_template_id=monitor.email_template_id)
    draft = Draft(user_id=user.user_id, conversation_id=conversation.id,
                  monitor_id=monitor.id, status="draft",
                  spec=monitor.spec, spec_hash=monitor.spec_hash, spec_revision=1,
                  settings=settings.model_dump(mode="json"),
                  settings_hash=content_hash(settings), settings_revision=1)
    session.add(draft)
    await session.flush()
    return conversation, draft


# ---- previews ---------------------------------------------------------------

async def start_preview(session: AsyncSession, user: CurrentUser, draft_id: UUID) -> Job:
    draft = await require_draft(session, user, draft_id, lock=True)
    spec = _spec(draft)
    validate_url(spec.url)
    existing = await session.scalar(select(Job).where(Job.draft_id == draft.id,
        Job.kind == "preview", Job.revision == draft.spec_revision,
        Job.status.in_(("queued", "running"))))
    if existing is not None:
        return existing
    return await jobs.enqueue(session, user_id=draft.user_id, kind="preview",
        draft_id=draft.id, revision=draft.spec_revision, url=spec.url,
        spec=spec.model_dump(mode="json"), conversation_id=draft.conversation_id)


def _extraction_preview(draft: Draft, spec: MonitorSpec, result: dict,
                        now, ttl_minutes: int) -> dict:
    fields = result.get("fields") or {}
    preview = {
        "preview_id": str(uuid4()),
        "spec_revision": draft.spec_revision,
        "spec_hash": content_hash(spec),
        "extracted_data": fields,
        "coverage": result.get("coverage") or {},
        "final_url": result.get("final_url"),
        "evidence_refs": result.get("evidence_refs") or [],
        "rule_simulation": evaluate_rules(spec, None, fields, {}),
        "source": (result.get("analysis") or {}).get("source"),
        "warnings": list(result.get("warnings") or []),
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat(),
    }
    return preview


async def build_preview(session: AsyncSession, draft: Draft, job: Job) -> dict:
    """Worker-side: freeze the real collection result, then refresh the mail preview."""
    if (draft.status != "draft" or job.revision != draft.spec_revision
            or job.spec != draft.spec):
        raise DomainError("stale_revision", 409)
    spec = _spec(draft)
    now = utc_now()
    ttl = get_settings().preview_ttl_minutes
    stored = ExtractionPreview.model_validate(
        _extraction_preview(draft, spec, job.result or {}, now, ttl)).model_dump(mode="json")
    _clear_delivery_preview(draft)
    draft.extraction_preview = stored
    try:
        await build_delivery_preview(session, draft)
    except DomainError as exc:
        if exc.code not in DELIVERY_WARNINGS:
            raise
        stored = {**stored, "warnings": [*stored["warnings"],
                                         f"delivery_preview_failed:{exc.code}"]}
        draft.extraction_preview = stored
    draft.extraction_preview_hash = extraction_hash(stored)
    draft.extraction_preview_expires_at = now + timedelta(minutes=ttl)
    await session.flush()
    return stored


def _delivery_payload(draft: Draft, spec: MonitorSpec, settings: DeliverySettings,
                      fields: dict) -> dict:
    return {
        "monitor": {"id": str(draft.monitor_id or draft.id), "name": spec.name,
                    "url": spec.url,
                    "timezone": (settings.schedule.timezone if settings.schedule else "") or "UTC"},
        "event": {"id": str(uuid4()), "type": "content_changed",
                  "detected_at": utc_now().isoformat()},
        "change": {"before": None, "after": fields,
                   "summary": "预览：首次成功采集只会建立基线，不发送业务通知。",
                   "differences": [], "labels": {}},
        "fields": fields,
        "evidence_url": f"{get_settings().app_origin}/app",
    }


async def build_delivery_preview(session: AsyncSession, draft: Draft) -> dict | None:
    """Render what the mail will look like for the current settings and template."""
    if draft.extraction_preview is None:
        raise DomainError("preview_missing", 409)
    settings = _settings(draft)
    if not settings.notification_group_ids:
        return None
    spec = _spec(draft)
    recipients = await notifications.load_recipients(
        session, settings.notification_group_ids, lock=True)
    config: EmailTemplateConfig | None = None
    template_id: UUID | None = None
    template_name: str | None = None
    if settings.email_template_id is not None:
        template_id, config, template_name = await _resolve_template(
            session, settings.email_template_id, spec)
    template_hash = content_hash(config.model_dump(mode="json") if config else None)
    payload = _delivery_payload(draft, spec, settings,
                               draft.extraction_preview.get("extracted_data") or {})
    rendered: list[dict] = []
    warnings: list[str] = []
    for event_type in sorted(_event_types(spec)):
        message = render_email(event_type, {**payload,
            "event": {**payload["event"], "type": event_type}}, config)
        rendered.append({"event_type": event_type, "subject": message["subject"],
                         "html": message["html"], "text": message["text"],
                         "preview_html": sanitize_preview(message["html"])})
    now = utc_now()
    ttl = get_settings().preview_ttl_minutes
    preview = {
        "preview_id": str(uuid4()),
        "settings_revision": draft.settings_revision,
        "settings_hash": content_hash(settings),
        "template_id": str(template_id) if template_id is not None else None,
        "template_name": template_name,
        "template_hash": template_hash,
        "rendered_emails": rendered,
        "recipients": notifications.recipients_emails(recipients),
        "recipient_sources": recipients,
        "warnings": warnings,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=ttl)).isoformat(),
    }
    stored = DeliveryPreview.model_validate(preview).model_dump(mode="json")
    digest = delivery_hash(stored)
    draft.delivery_preview = stored
    draft.delivery_preview_hash = digest
    draft.delivery_preview_expires_at = now + timedelta(minutes=ttl)
    await session.flush()
    return stored


async def _resolve_template(session: AsyncSession, template_id: UUID,
                            spec: MonitorSpec) -> tuple[UUID, EmailTemplateConfig, str]:
    try:
        template = await templates.get_template(session, template_id)
    except DomainError:
        raise DomainError("template_unavailable", 409) from None
    config = templates.config_of(template)
    _validate_template(config, spec)
    return template.id, config, template.name


def _validate_template(config: EmailTemplateConfig, spec: MonitorSpec) -> None:
    try:
        validate_template_for_spec(config, spec)
    except TemplateIncompatible as exc:
        raise DomainError("template_incompatible", 409,
                          details={"fields": exc.fields}) from None


# ---- validation -------------------------------------------------------------

def validate_extraction_preview(draft: Draft) -> dict:
    """Caller holds the draft lock, serializing edit, preview and publication."""
    if draft.extraction_preview is None or draft.spec is None:
        raise DomainError("preview_missing", 409)
    preview = dict(draft.extraction_preview)
    if preview.get("spec_revision") != draft.spec_revision:
        raise DomainError("stale_revision", 409)
    if draft.extraction_preview_expires_at is None \
            or draft.extraction_preview_expires_at <= utc_now():
        raise DomainError("preview_expired", 409)
    if preview.get("spec_hash") != content_hash(_spec(draft)) \
            or draft.spec_hash != preview.get("spec_hash"):
        raise DomainError("stale_revision", 409)
    if extraction_hash(preview) != draft.extraction_preview_hash:
        raise DomainError("preview_stale", 409, "Preview result changed; preview again")
    return preview


async def validate_delivery_preview(session: AsyncSession, draft: Draft) -> dict:
    """The rendered mail must still match the current settings, template and people."""
    if draft.delivery_preview is None:
        raise DomainError("preview_missing", 409)
    preview = dict(draft.delivery_preview)
    if preview.get("settings_revision") != draft.settings_revision:
        raise DomainError("stale_revision", 409)
    if draft.delivery_preview_expires_at is None \
            or draft.delivery_preview_expires_at <= utc_now():
        raise DomainError("preview_expired", 409)
    if delivery_hash(preview) != draft.delivery_preview_hash:
        raise DomainError("preview_stale", 409, "Preview result changed; preview again")
    settings = _settings(draft)
    template_hash = content_hash(None)
    if settings.email_template_id is not None:
        try:
            template = await templates.get_template(session, settings.email_template_id)
        except DomainError:
            raise DomainError("template_unavailable", 409) from None
        template_hash = content_hash(templates.config_of(template).model_dump(mode="json"))
    if preview.get("template_hash") != template_hash:
        raise DomainError("preview_stale", 409, "The selected template changed; preview again")
    if not settings.notification_group_ids:
        raise DomainError("settings_incomplete", 409,
                          details={"missing": ["notification_group_ids"]})
    recipients = await notifications.load_recipients(
        session, settings.notification_group_ids, lock=True)
    if (notifications.recipients_emails(recipients) != preview.get("recipients")
            or recipients != preview.get("recipient_sources")):
        raise DomainError("preview_stale", 409, "Notification recipients changed; preview again")
    return preview


# ---- publication ------------------------------------------------------------

def _contract(spec: dict[str, Any]) -> str:
    """The collection contract, ignoring the display name, decides a version bump."""
    return content_hash({**spec, "name": None})


async def publish_draft(session: AsyncSession, user: CurrentUser, *, conversation_id: UUID,
                        draft_id: UUID, spec_revision: int, settings_revision: int,
                        extraction_preview_hash: str,
                        delivery_preview_hash: str) -> Monitor:
    conversation = await session.get(Conversation, conversation_id,
                                     with_for_update=True, populate_existing=True)
    require_owner(user, conversation)
    row = await require_draft(session, user, draft_id)
    monitor = None
    if row.monitor_id is not None:
        monitor = require_owner(user, await session.get(Monitor, row.monitor_id,
            with_for_update=True, populate_existing=True))
    draft = await require_draft(session, user, draft_id, lock=True)
    if draft.conversation_id != conversation_id:
        raise DomainError("not_found", 404)
    if draft.spec_revision != spec_revision or draft.settings_revision != settings_revision:
        raise DomainError("stale_revision", 409)
    if draft.status == "published" and monitor is not None:
        return monitor
    settings = _settings(draft)
    schedule = settings.schedule
    missing = [name for name, present in (
        ("notification_group_ids", bool(settings.notification_group_ids)),
        ("schedule", schedule is not None)) if not present]
    if missing or schedule is None:
        raise DomainError("settings_incomplete", 409, details={"missing": missing})
    if draft.extraction_preview_hash is None or \
            extraction_preview_hash != draft.extraction_preview_hash:
        raise DomainError("preview_stale", 409)
    if draft.delivery_preview_hash is None or delivery_preview_hash != draft.delivery_preview_hash:
        raise DomainError("preview_stale", 409)
    pending = await session.scalar(select(Job.id).where(
        Job.draft_id == draft.id, Job.kind == "preview",
        Job.revision == draft.spec_revision, Job.status.in_(("queued", "running"))))
    if pending is not None:
        raise DomainError("preview_not_ready", 409)
    spec = _spec(draft)
    validate_url(spec.url)
    validate_extraction_preview(draft)
    delivery = await validate_delivery_preview(session, draft)
    template_id, template_name, snapshot = await _template_snapshot(session, settings, spec)
    if monitor is not None and _contract(monitor.spec or {}) == _contract(
            spec.model_dump(mode="json")):
        _apply_settings(monitor, spec, settings, schedule, template_id, template_name,
                        snapshot)
        draft.published_spec_version = None
    elif monitor is not None:
        _apply_contract(monitor, spec, draft.spec_hash)
        _apply_settings(monitor, spec, settings, schedule, template_id, template_name,
                        snapshot)
        draft.published_spec_version = monitor.spec_version
    else:
        await _enforce_quota(session, draft.user_id)
        monitor = Monitor(user_id=draft.user_id, draft_id=draft.id, name=spec.name,
            url=spec.url, status="active", spec=spec.model_dump(mode="json"), spec_version=1,
            spec_hash=draft.spec_hash, collection_mode=spec.collection_mode,
            interval_seconds=schedule.interval_seconds,
            timezone=schedule.timezone,
            notification_group_ids=[str(item) for item in settings.notification_group_ids],
            email_template_id=template_id, email_template_name=template_name,
            email_template=snapshot,
            approved_recipients=delivery["recipient_sources"],
            baseline_status="pending_first_success", rule_state={}, next_run_at=utc_now())
        session.add(monitor)
        await session.flush()
        draft.published_spec_version = monitor.spec_version
    draft.status = "published"
    draft.monitor_id = monitor.id
    await session.flush()
    return monitor


def _apply_contract(monitor: Monitor, spec: MonitorSpec, spec_hash: str | None) -> None:
    """A changed collection contract resets the baseline and the collection history."""
    monitor.spec = spec.model_dump(mode="json")
    monitor.spec_hash = spec_hash or content_hash(spec)
    monitor.spec_version += 1
    monitor.name, monitor.url = spec.name, spec.url
    monitor.collection_mode = spec.collection_mode
    monitor.baseline_snapshot_id = None
    monitor.baseline_status = "pending_first_success"
    monitor.rule_state = {}
    monitor.health_status, monitor.failure_fingerprint = "healthy", None
    monitor.next_run_at = utc_now()


def _apply_settings(monitor: Monitor, spec: MonitorSpec, settings: DeliverySettings,
                    schedule: Schedule, template_id: UUID | None,
                    template_name: str | None, snapshot: dict | None) -> None:
    """Who is told, how often and in which design; the baseline is untouched."""
    interval = schedule.interval_seconds
    monitor.interval_seconds = interval
    monitor.timezone = schedule.timezone
    monitor.notification_group_ids = [str(item) for item in settings.notification_group_ids]
    monitor.email_template_id = template_id
    monitor.email_template_name = template_name
    monitor.email_template = snapshot
    if monitor.name != spec.name:
        # The name lives in the contract; keep the stored one consistent.
        monitor.name = spec.name
        monitor.spec = spec.model_dump(mode="json")
        monitor.spec_hash = content_hash(spec)
    soonest = utc_now() + timedelta(seconds=interval)
    monitor.next_run_at = min(monitor.next_run_at, soonest)


async def _template_snapshot(session: AsyncSession, settings: DeliverySettings,
                             spec: MonitorSpec) -> tuple[UUID | None, str | None, dict | None]:
    if settings.email_template_id is None:
        return None, None, None
    template_id, config, name = await _resolve_template(session, settings.email_template_id, spec)
    return template_id, name, {"id": str(template_id), "name": name,
                               "config": config.model_dump(mode="json")}


async def _enforce_quota(session: AsyncSession, user_id: UUID) -> None:
    settings = get_settings()
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())
    active = await session.scalar(select(func.count()).select_from(Monitor).where(
        Monitor.user_id == user_id, Monitor.status == "active"))
    if (active or 0) >= settings.max_active_monitors:
        raise DomainError("quota_exceeded", 409)


def monitor_result(monitor: Monitor) -> CreateMonitorResult:
    return CreateMonitorResult(monitor_id=monitor.id, status=monitor.status,
        baseline_status=monitor.baseline_status, next_run_at=monitor.next_run_at)
