"""Read-only Server-Sent Events for conversation snapshots."""
import asyncio
import hashlib
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.agent import live_text
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.services import conversations

router = APIRouter(prefix="/api/v1", tags=["conversations"])
_FRAME_SECONDS = 0.05
_DB_POLL_SECONDS = 1.0
_HEARTBEAT_SECONDS = 15.0


@router.get("/conversations/{conversation_id}/stream", response_class=StreamingResponse)
async def stream_conversation(conversation_id: UUID, request: Request,
                              session: DatabaseSession, user: AuthenticatedUser):
    await conversations.require_conversation(session, user, conversation_id)

    async def events():
        previous = request.headers.get("last-event-id", "")
        heartbeat = 0.0
        snapshot = None
        base_partial = {}
        last_db_read = 0.0
        yield "retry: 1000\n\n"
        try:
            while not await request.is_disconnected():
                now = asyncio.get_running_loop().time()
                if snapshot is None or now - last_db_read >= _DB_POLL_SECONDS:
                    async with get_session_factory()() as active:
                        snapshot = await conversations.snapshot(active, user, conversation_id)
                    base_partial = {job.id: job.partial_text for job in snapshot.jobs}
                    last_db_read = now
                for job in snapshot.jobs:
                    pending = live_text.pending(job.id) if job.status == "running" else ""
                    job.partial_text = base_partial.get(job.id, job.partial_text) + pending
                body = snapshot.model_dump_json()
                event_id = hashlib.sha256(body.encode("utf-8")).hexdigest()
                if event_id != previous:
                    yield f"id: {event_id}\nevent: conversation\ndata: {body}\n\n"
                    previous = event_id
                now = asyncio.get_running_loop().time()
                if now - heartbeat >= _HEARTBEAT_SECONDS:
                    yield ": keepalive\n\n"
                    heartbeat = now
                await asyncio.sleep(_FRAME_SECONDS)
        except DomainError as exc:
            yield f"event: error\ndata: {{\"code\":\"{exc.code}\"}}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })
