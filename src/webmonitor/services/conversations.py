"""Conversation reads and the two commands: post a message, approve a draft."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Draft, Job, Message, Monitor, utc_now
from webmonitor.schemas.api import (
    ConversationSnapshot,
    ConversationView,
    DraftView,
    JobView,
    Limits,
    MessageView,
    Page,
)
from webmonitor.security.auth import CurrentUser, require_owner
from webmonitor.services import jobs

ACTIVE = ("queued", "running")
AGENT_HISTORY = 20


async def require_conversation(session: AsyncSession, user: CurrentUser, conversation_id: UUID,
                               *, lock: bool = False) -> Conversation:
    query = select(Conversation).where(Conversation.id == conversation_id)
    if lock:
        query = query.with_for_update()
    conversation = await session.scalar(query.execution_options(populate_existing=True))
    return require_owner(user, conversation)


async def list_conversations(session: AsyncSession, user: CurrentUser, limit: int,
                             offset: int) -> Page[ConversationView]:
    query = select(Conversation)
    if user.role != "admin":
        query = query.where(Conversation.user_id == user.user_id)
    rows = (await session.scalars(query.order_by(Conversation.updated_at.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[ConversationView](items=[_conversation_view(row) for row in rows],
                                  total=total or 0)


async def create_conversation(session: AsyncSession, user: CurrentUser,
                              title: str | None = None) -> ConversationView:
    conversation = Conversation(user_id=user.user_id, title=(title or None))
    session.add(conversation)
    await session.flush()
    return _conversation_view(conversation)


def _conversation_view(conversation: Conversation) -> ConversationView:
    return ConversationView(id=conversation.id, title=conversation.title,
        created_at=conversation.created_at, updated_at=conversation.updated_at)


def job_view(job: Job) -> JobView:
    return JobView(id=job.id, kind=job.kind, status=job.status,
        conversation_id=job.conversation_id, draft_id=job.draft_id, monitor_id=job.monitor_id,
        revision=job.revision, url=job.url, partial_text=job.partial_text or "",
        steps=list(job.steps or []), attempts=list(job.attempts or []),
        attempt_count=job.attempt_count, started_at=job.started_at,
        finished_at=job.finished_at, error_code=job.error_code,
        error_message=job.error_message, created_at=job.created_at)


def draft_view(draft: Draft) -> DraftView:
    return DraftView(id=draft.id, conversation_id=draft.conversation_id,
        revision=draft.revision, status=draft.status, spec=draft.spec,
        spec_hash=draft.spec_hash, preview=draft.preview,
        preview_expires_at=draft.preview_expires_at, monitor_id=draft.monitor_id,
        created_at=draft.created_at, updated_at=draft.updated_at)


async def snapshot(session: AsyncSession, user: CurrentUser,
                   conversation_id: UUID) -> ConversationSnapshot:
    conversation = await require_conversation(session, user, conversation_id)
    messages = (await session.scalars(select(Message).where(
        Message.conversation_id == conversation.id).order_by(Message.created_at, Message.id))).all()
    runs = (await session.scalars(select(Job).where(Job.conversation_id == conversation.id,
        Job.kind == "agent").order_by(Job.created_at.desc(), Job.id.desc())
        .limit(AGENT_HISTORY))).all()
    drafts = (await session.scalars(select(Draft).where(
        Draft.conversation_id == conversation.id).order_by(Draft.created_at, Draft.id))).all()
    settings = get_settings()
    return ConversationSnapshot(
        conversation=_conversation_view(conversation),
        messages=[MessageView(id=row.id, role=row.role, content=row.content, job_id=row.job_id,
                              client_message_id=row.client_message_id, created_at=row.created_at)
                  for row in messages],
        jobs=[job_view(row) for row in reversed(runs)],
        drafts=[draft_view(row) for row in drafts],
        limits=Limits(message_max_chars=settings.message_max_chars,
                      preview_ttl_minutes=settings.preview_ttl_minutes))


async def post_message(session: AsyncSession, user: CurrentUser, conversation_id: UUID, *,
                       content: str, client_message_id: str) -> JobView:
    settings = get_settings()
    content = content.strip()
    if not content:
        raise DomainError("message_empty", 422)
    if len(content) > settings.message_max_chars:
        raise DomainError("message_too_long", 422,
                          details={"limit": settings.message_max_chars})
    conversation = await require_conversation(session, user, conversation_id, lock=True)
    existing = await session.scalar(select(Message).where(
        Message.conversation_id == conversation.id,
        Message.client_message_id == client_message_id))
    if existing is not None:
        if existing.content != content:
            raise DomainError("idempotency_conflict", 409)
        if existing.job_id is None:
            raise DomainError("idempotency_conflict", 409)
        job = await session.get(Job, existing.job_id)
        return job_view(job)
    active = await session.scalar(select(Job).where(Job.conversation_id == conversation.id,
        Job.kind == "agent", Job.status.in_(ACTIVE)))
    if active is not None:
        raise DomainError("run_in_progress", 409, details={"job_id": str(active.id)})
    job = await jobs.enqueue(session, user_id=user.user_id, kind="agent",
                             conversation_id=conversation.id)
    session.add(Message(conversation_id=conversation.id, job_id=job.id, user_id=user.user_id,
        client_message_id=client_message_id, role="user", content=content))
    conversation.updated_at = utc_now()
    await session.flush()
    return job_view(job)


async def active_job(session: AsyncSession, conversation_id: UUID) -> Job | None:
    return await session.scalar(select(Job).where(Job.conversation_id == conversation_id,
        Job.kind == "agent", Job.status.in_(ACTIVE)))


async def cancel(session: AsyncSession, user: CurrentUser, conversation_id: UUID) -> JobView:
    await require_conversation(session, user, conversation_id, lock=True)
    job = await session.scalar(select(Job).where(Job.conversation_id == conversation_id,
        Job.kind == "agent", Job.status.in_(ACTIVE)).with_for_update()
        .execution_options(populate_existing=True))
    if job is None:
        raise DomainError("run_not_active", 409)
    await jobs.cancel(session, job)
    return job_view(job)


async def approve(session: AsyncSession, user: CurrentUser, conversation_id: UUID, *,
                  draft_id: UUID, revision: int) -> Monitor:
    from webmonitor.services import drafts
    await require_conversation(session, user, conversation_id)
    return await drafts.publish_draft(session, user, conversation_id=conversation_id,
                                      draft_id=draft_id, revision=revision)
