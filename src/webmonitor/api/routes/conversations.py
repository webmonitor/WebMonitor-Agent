"""Conversation reads, message commands and draft approval."""
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import Job, Snapshot
from webmonitor.schemas.api import (
    ApproveRequest,
    ConversationCreate,
    ConversationSnapshot,
    ConversationView,
    CreateMonitorResult,
    DraftView,
    JobDetail,
    JobView,
    Page,
    PostMessageRequest,
)
from webmonitor.services import conversations, drafts
from webmonitor.services import monitors as monitor_service

router = APIRouter(prefix="/api/v1", tags=["conversations"])


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get("/conversations", response_model=Page[ConversationView])
async def list_conversations(session: DatabaseSession, user: AuthenticatedUser,
                             limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await conversations.list_conversations(session, user, limit, offset)


@router.post("/conversations", response_model=ConversationView, status_code=201)
async def create_conversation(payload: ConversationCreate, session: DatabaseSession,
                              user: AuthenticatedUser):
    result = await conversations.create_conversation(session, user, payload.title)
    await session.commit()
    return result


@router.get("/conversations/{conversation_id}", response_model=ConversationSnapshot)
async def snapshot(conversation_id: UUID, response: Response, session: DatabaseSession,
                   user: AuthenticatedUser):
    result = await conversations.snapshot(session, user, conversation_id)
    _no_store(response)
    return result


@router.post("/conversations/{conversation_id}/messages", response_model=JobView, status_code=202)
async def post_message(conversation_id: UUID, payload: PostMessageRequest, session: DatabaseSession,
                       user: AuthenticatedUser):
    result = await conversations.post_message(session, user, conversation_id,
        content=payload.content, client_message_id=payload.client_message_id)
    await session.commit()
    return result


@router.post("/conversations/{conversation_id}/cancel", response_model=JobView)
async def cancel(conversation_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    result = await conversations.cancel(session, user, conversation_id)
    await session.commit()
    return result


@router.post("/conversations/{conversation_id}/approve", response_model=CreateMonitorResult)
async def approve(conversation_id: UUID, payload: ApproveRequest, session: DatabaseSession,
                  user: AuthenticatedUser):
    monitor = await conversations.approve(session, user, conversation_id,
        draft_id=payload.draft_id, revision=payload.revision)
    result = drafts.monitor_result(monitor)
    await session.commit()
    return result


@router.get("/drafts/{draft_id}", response_model=DraftView)
async def read_draft(draft_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    return conversations.draft_view(await drafts.require_draft(session, user, draft_id))


@router.post("/drafts/{draft_id}/preview", response_model=JobView, status_code=202)
async def start_preview(draft_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    result = await drafts.start_preview(session, user, draft_id)
    view = conversations.job_view(result)
    await session.commit()
    return view


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def read_job(job_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    job = await session.get(Job, job_id)
    if job is None or (job.user_id != user.user_id and user.role != "admin"):
        raise DomainError("not_found", 404)
    snapshot = await session.scalar(select(Snapshot).where(Snapshot.job_id == job.id))
    return JobDetail(**conversations.job_view(job).model_dump(), result=job.result,
        snapshot=monitor_service.snapshot_record(snapshot) if snapshot is not None else None)


@router.post("/jobs/{job_id}/cancel", response_model=JobView)
async def cancel_job(job_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    job = await session.scalar(select(Job).where(Job.id == job_id).with_for_update()
        .execution_options(populate_existing=True))
    if job is None:
        raise DomainError("not_found", 404)
    if job.user_id != user.user_id and user.role != "admin":
        raise DomainError("forbidden", 403)
    from webmonitor.services import jobs as job_service
    await job_service.cancel(session, job)
    result = conversations.job_view(job)
    await session.commit()
    return result


@router.post("/monitors/{monitor_id}/drafts")
async def derive_draft(monitor_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    conversation, draft = await drafts.draft_from_monitor(session, user, monitor_id)
    result = {"conversation_id": str(conversation.id), "draft_id": str(draft.id),
              "revision": draft.revision}
    await session.commit()
    return result
