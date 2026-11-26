"""Authenticated snapshot SSE with lightweight process-local text deltas."""
import asyncio
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession, SESSION_COOKIE
from webmonitor.agent import live_text
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.services import accounts, conversations

router = APIRouter(prefix="/api/v1", tags=["conversations"])
_FRAME_SECONDS = 0.05
_DB_POLL_SECONDS = 1.0
_HEARTBEAT_SECONDS = 15.0


@router.get("/conversations/{conversation_id}/stream", response_class=StreamingResponse)
async def stream_conversation(conversation_id: UUID, request: Request,
                              session: DatabaseSession, user: AuthenticatedUser):
    session_token = request.cookies.get(SESSION_COOKIE)
    if not session_token:
        raise DomainError("unauthenticated", 401)
    try:
        await conversations.require_conversation(session, user, conversation_id)
    finally:
        # FastAPI otherwise keeps the request dependency open until the SSE body ends.
        await session.close()

    async def events():
        previous = request.headers.get("last-event-id", "")
        heartbeat = 0.0
        snapshot = None
        base_partial = {}
        emitted_deltas = {}
        last_db_read = 0.0
        yield "retry: 1000\n\n"
        try:
            while not await request.is_disconnected():
                now = asyncio.get_running_loop().time()
                if snapshot is None or now - last_db_read >= _DB_POLL_SECONDS:
                    async with get_session_factory()() as active:
                        active_user = await accounts.resolve_session(active, session_token)
                        snapshot = await conversations.snapshot(active, active_user, conversation_id)
                    base_partial = {job.id: job.partial_text for job in snapshot.jobs}
                    body = snapshot.model_dump_json()
                    event_id = hashlib.sha256(body.encode("utf-8")).hexdigest()
                    if event_id != previous:
                        yield f"id: {event_id}\nevent: conversation\ndata: {body}\n\n"
                        previous = event_id
                    last_db_read = now
                active_delta = False
                for job in snapshot.jobs:
                    if job.status != "running":
                        emitted_deltas.pop(job.id, None)
                        continue
                    active_delta = True
                    pending = live_text.pending(job.id)
                    if not pending:
                        continue
                    partial_text = base_partial.get(job.id, job.partial_text) + pending
                    if emitted_deltas.get(job.id) != partial_text:
                        data = json.dumps({"job_id": str(job.id), "partial_text": partial_text},
                                          ensure_ascii=False, separators=(",", ":"))
                        yield f"event: conversation_delta\ndata: {data}\n\n"
                        emitted_deltas[job.id] = partial_text
                now = asyncio.get_running_loop().time()
                if now - heartbeat >= _HEARTBEAT_SECONDS:
                    yield ": keepalive\n\n"
                    heartbeat = now
                await asyncio.sleep(_FRAME_SECONDS if active_delta else _DB_POLL_SECONDS)
        except DomainError as exc:
            data = json.dumps({"code": exc.code}, separators=(",", ":"))
            yield f"event: error\ndata: {data}\n\n"
            return

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })
