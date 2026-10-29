"""Draft revisions, real previews and the single publication path."""
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.collection.diff import evaluate_rules
from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Draft, Job, Monitor, User, utc_now
from webmonitor.notifications.rendering import render_email, sanitize_preview
from webmonitor.schemas.api import CreateMonitorResult
from webmonitor.schemas.monitors import DraftSpec, content_hash
from webmonitor.security.auth import CurrentUser, require_owner
from webmonitor.security.egress import validate_url
from webmonitor.services import jobs, notifications

PREVIEW_KEYS = ("revision", "spec_hash", "extracted_data", "coverage", "evidence_refs",
                "rule_simulation", "rendered_emails", "recipients", "warnings")


async def require_draft(session: AsyncSession, user: CurrentUser, draft_id: UUID,
                        *, lock: bool = False) -> Draft:
    query = select(Draft).where(Draft.id == draft_id)
    if lock:
        query = query.with_for_update()
    return require_owner(user, await session.scalar(
        query.execution_options(populate_existing=True)))


def _spec(draft: Draft) -> DraftSpec:
    if draft.spec is None:
        raise DomainError("draft_empty", 409)
    return DraftSpec.model_validate(draft.spec)


async def save_draft(session: AsyncSession, user: CurrentUser, *, conversation_id: UUID,
                     spec: DraftSpec, draft_id: UUID | None = None) -> Draft:
    spec = DraftSpec.model_validate(spec)
    conversation = await session.scalar(select(Conversation).where(
        Conversation.id == conversation_id).with_for_update()
        .execution_options(populate_existing=True))
    require_owner(user, conversation)
    if draft_id is None:
        draft = Draft(user_id=user.user_id, conversation_id=conversation.id, revision=0,
                      status="draft")
        session.add(draft)
        await session.flush()
    else:
        draft = await require_draft(session, user, draft_id, lock=True)
        if draft.conversation_id != conversation.id:
            raise DomainError("not_found", 404)
        if draft.status == "discarded":
            raise DomainError("draft_not_editable", 409)
    draft.revision += 1
    draft.spec = spec.model_dump(mode="json")
    draft.spec_hash = content_hash(spec)
    draft.preview = None
    draft.preview_hash = None
    draft.preview_expires_at = None
    draft.status = "draft"
    conversation.updated_at = utc_now()
    # An edited spec invalidates every in-flight preview of the same draft.
    await jobs.cancel_pending(session, draft_id=draft.id)
    await session.flush()
    return draft


async def draft_from_monitor(session: AsyncSession, user: CurrentUser,
                             monitor_id: UUID) -> tuple[Conversation, Draft]:
    monitor = require_owner(user, await session.get(Monitor, monitor_id))
    conversation = Conversation(user_id=user.user_id,
        title=f"修改监控：{monitor.name}"[:200])
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.user_id, conversation_id=conversation.id,
                  monitor_id=monitor.id, revision=0, status="draft")
    session.add(draft)
    await session.flush()
    await save_draft(session, user, conversation_id=conversation.id,
                     spec=DraftSpec.model_validate(monitor.spec), draft_id=draft.id)
    return conversation, draft


async def start_preview(session: AsyncSession, user: CurrentUser, draft_id: UUID) -> Job:
    draft = await require_draft(session, user, draft_id, lock=True)
    spec = _spec(draft)
    validate_url(spec.url)
    existing = await session.scalar(select(Job).where(Job.draft_id == draft.id,
        Job.kind == "preview", Job.revision == draft.revision,
        Job.status.in_(("queued", "running"))))
    if existing is not None:
        return existing
    return await jobs.enqueue(session, user_id=draft.user_id, kind="preview",
        draft_id=draft.id, revision=draft.revision, url=spec.url,
        spec=spec.model_dump(mode="json"), conversation_id=draft.conversation_id)


def _event_types(spec: DraftSpec) -> set[str]:
    types = {"run_failed", "recovered"}
    fields = {field.name: field for field in spec.fields}
    for rule in spec.change_rules.rules:
        kind = fields[rule.field].type
        types.add("price_changed" if kind == "money"
                  else "list_changed" if kind == "list" else "content_changed")
    return types


def preview_hash(payload: dict) -> str:
    return content_hash({key: payload.get(key) for key in PREVIEW_KEYS})


async def build_preview(session: AsyncSession, draft: Draft, job: Job) -> dict:
    """Worker-side: freeze the real collection result into the draft's preview."""
    spec = _spec(draft)
    result = job.result or {}
    fields = result.get("fields") or {}
    recipients = await notifications.load_recipients(
        session, spec.notification_group_ids or [])
    emails = notifications.recipients_emails(recipients)
    simulation = evaluate_rules(spec, None, fields, {})
    event_id = uuid4()
    payload = {
        "monitor": {"id": str(draft.monitor_id or draft.id), "name": spec.name, "url": spec.url},
        "event": {"id": str(event_id), "type": "price_changed",
                  "detected_at": utc_now().isoformat()},
        "change": {"before": None, "after": fields,
                   "summary": "预览：首次成功采集只会建立基线，不发送业务通知。"},
        "fields": fields,
        "evidence_url": f"{get_settings().app_origin}/app",
    }
    rendered = []
    skipped = []
    for event_type in sorted(_event_types(spec)):
        try:
            message = render_email(event_type, {**payload,
                "event": {**payload["event"], "type": event_type}})
        except DomainError as exc:
            if exc.code != "template_contract_failed":
                raise
            # A money field that is not named current_price cannot fill the price
            # template; say so before approval instead of failing silently later.
            skipped.append(f"template_contract_failed:{event_type}")
            continue
        rendered.append({"event_type": event_type, "subject": message["subject"],
                         "html": message["html"], "text": message["text"],
                         "preview_html": sanitize_preview(message["html"])})
    warnings = list(result.get("warnings") or []) + skipped
    now = utc_now()
    preview = {
        "revision": draft.revision,
        "spec_hash": draft.spec_hash,
        "extracted_data": fields,
        "coverage": result.get("coverage") or {},
        "final_url": result.get("final_url"),
        "evidence_refs": result.get("evidence_refs") or [],
        "rule_simulation": simulation,
        "rendered_emails": rendered,
        "recipients": emails,
        "warnings": warnings,
        "created_at": now.isoformat(),
        "expires_at": None,
    }
    return await save_preview(session, draft, preview, ttl_minutes=get_settings().preview_ttl_minutes)


async def save_preview(session: AsyncSession, draft: Draft, preview: dict, *,
                       ttl_minutes: int) -> dict:
    now = utc_now()
    preview["created_at"] = now.isoformat()
    preview["expires_at"] = (now + timedelta(minutes=ttl_minutes)).isoformat()
    draft.preview = preview
    draft.preview_hash = preview_hash(preview)
    draft.preview_expires_at = now + timedelta(minutes=ttl_minutes)
    await session.flush()
    return preview


async def validate_preview(session: AsyncSession, draft: Draft) -> dict:
    """Caller holds the draft lock, serializing edit, preview and publication."""
    if draft.preview is None or draft.spec is None:
        raise DomainError("preview_missing", 409)
    preview = dict(draft.preview)
    if preview.get("revision") != draft.revision:
        raise DomainError("stale_revision", 409)
    if (draft.preview_expires_at is None or draft.preview_expires_at <= utc_now()):
        raise DomainError("preview_expired", 409)
    spec = DraftSpec.model_validate(draft.spec)
    if preview.get("spec_hash") != content_hash(spec) or draft.spec_hash != preview.get("spec_hash"):
        raise DomainError("stale_revision", 409)
    if preview_hash(preview) != draft.preview_hash:
        raise DomainError("preview_stale", 409, "Preview result changed; preview again")
    recipients = await notifications.load_recipients(session, spec.notification_group_ids or [])
    if notifications.recipients_emails(recipients) != preview.get("recipients"):
        raise DomainError("preview_stale", 409, "Notification recipients changed; preview again")
    return preview


async def publish_draft(session: AsyncSession, user: CurrentUser, *, conversation_id: UUID,
                        draft_id: UUID, revision: int) -> Monitor:
    draft = await require_draft(session, user, draft_id, lock=True)
    if draft.conversation_id != conversation_id:
        raise DomainError("not_found", 404)
    if draft.monitor_id is not None:
        monitor = await session.get(Monitor, draft.monitor_id)
        if monitor is not None and draft.status == "published" and revision == draft.revision:
            return monitor
    if draft.revision != revision:
        raise DomainError("stale_revision", 409)
    await validate_preview(session, draft)
    spec = DraftSpec.model_validate(draft.spec)
    validate_url(spec.url)
    if draft.monitor_id is not None:
        monitor = require_owner(user, await session.get(Monitor, draft.monitor_id))
        monitor.spec = spec.model_dump(mode="json")
        monitor.spec_hash = draft.spec_hash
        monitor.spec_version += 1
        monitor.name, monitor.url = spec.name, spec.url
        monitor.collection_mode = spec.collection_mode
        monitor.interval_seconds = spec.schedule.interval_seconds
        monitor.timezone = spec.schedule.timezone
        monitor.notification_group_ids = [str(item) for item in spec.notification_group_ids]
        monitor.next_run_at = utc_now()
        # A new spec version starts a new baseline: the previous snapshot, rule
        # indexes and failure fingerprint describe a different contract.
        monitor.baseline_status = "pending_first_success"
        monitor.baseline_snapshot_id = None
        monitor.rule_state = {}
        monitor.health_status, monitor.failure_fingerprint = "healthy", None
        await jobs.cancel_pending(session, monitor_id=monitor.id)
    else:
        await _enforce_quota(session, draft.user_id)
        monitor = Monitor(user_id=draft.user_id, draft_id=draft.id, name=spec.name,
            url=spec.url, status="active", spec=spec.model_dump(mode="json"), spec_version=1,
            spec_hash=draft.spec_hash, collection_mode=spec.collection_mode,
            interval_seconds=spec.schedule.interval_seconds, timezone=spec.schedule.timezone,
            notification_group_ids=[str(item) for item in spec.notification_group_ids],
            baseline_status="pending_first_success", rule_state={}, next_run_at=utc_now())
        session.add(monitor)
        await session.flush()
    draft.status = "published"
    draft.monitor_id = monitor.id
    await session.flush()
    return monitor


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
