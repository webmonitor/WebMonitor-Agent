"""Bounded conversation history and independently authenticated live deltas."""
import asyncio
import json
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from webmonitor.agent import live_text
from webmonitor.api.routes import streams
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.models import Conversation, Job, Message, Session as AuthSession, User, utc_now
from webmonitor.schemas.api import ConversationSnapshot
from webmonitor.security.auth import CurrentUser
from webmonitor.services import accounts, conversations


class StreamRequest:
    def __init__(self, token):
        self.cookies = {"wm_session": token}
        self.headers = {}
        self.disconnected = False

    async def is_disconnected(self):
        return self.disconnected


async def stream_seed(session):
    token = uuid4().hex
    user = User(email=f"{uuid4().hex}@example.com", display_name="Stream",
                password_hash="not-a-login-hash", role="admin")
    session.add(user)
    await session.flush()
    conversation = Conversation(user_id=user.id, title="Live")
    session.add(conversation)
    await session.flush()
    auth = AuthSession(user_id=user.id, token_hash=accounts.token_hash(token),
                       expires_at=utc_now() + timedelta(hours=1))
    session.add(auth)
    await session.commit()
    return token, user, conversation, auth


async def event_payload(iterator, name):
    for _ in range(20):
        chunk = await asyncio.wait_for(anext(iterator), timeout=1)
        if f"event: {name}\n" not in chunk:
            continue
        line = next(line for line in chunk.splitlines() if line.startswith("data: "))
        return json.loads(line.removeprefix("data: "))
    raise AssertionError(f"SSE event {name} was not emitted")


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["revoked", "expired", "deactivated"])
async def test_stream_reauthenticates_and_closes_after_session_loss(
        session, monkeypatch, revocation):
    token, user, conversation, auth = await stream_seed(session)
    monkeypatch.setattr(streams, "_DB_POLL_SECONDS", 0)
    response = await streams.stream_conversation(
        conversation.id, StreamRequest(token), session,
        CurrentUser(user_id=user.id, role=user.role),
    )
    iterator = response.body_iterator
    assert await anext(iterator) == "retry: 1000\n\n"
    assert (await event_payload(iterator, "conversation"))["conversation"]["title"] == "Live"

    async with get_session_factory()() as active:
        stored_auth = await active.get(AuthSession, auth.id)
        stored_user = await active.get(User, user.id)
        if revocation == "revoked":
            stored_auth.revoked_at = utc_now()
        elif revocation == "expired":
            stored_auth.expires_at = utc_now() - timedelta(seconds=1)
        else:
            stored_user.active = False
        await active.commit()

    assert await event_payload(iterator, "error") == {"code": "unauthenticated"}
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)


@pytest.mark.asyncio
async def test_live_delta_does_not_mutate_or_reserialize_the_db_snapshot(session, monkeypatch):
    token, user, conversation, _ = await stream_seed(session)
    job = Job(user_id=user.id, kind="agent", status="running",
              conversation_id=conversation.id, partial_text="stored")
    session.add(job)
    await session.commit()
    monkeypatch.setattr(streams, "_FRAME_SECONDS", 0)
    monkeypatch.setattr(streams, "_DB_POLL_SECONDS", 60)
    serializations = 0
    original = ConversationSnapshot.model_dump_json

    def counted(self, *args, **kwargs):
        nonlocal serializations
        serializations += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ConversationSnapshot, "model_dump_json", counted)
    live_text.append(job.id, " live")
    response = await streams.stream_conversation(
        conversation.id, StreamRequest(token), session,
        CurrentUser(user_id=user.id, role=user.role),
    )
    iterator = response.body_iterator
    try:
        snapshot = await event_payload(iterator, "conversation")
        assert snapshot["jobs"][0]["partial_text"] == "stored"
        assert await event_payload(iterator, "conversation_delta") == {
            "job_id": str(job.id), "partial_text": "stored live",
        }
        live_text.append(job.id, " more")
        assert await event_payload(iterator, "conversation_delta") == {
            "job_id": str(job.id), "partial_text": "stored live more",
        }
        assert serializations == 1
    finally:
        await iterator.aclose()
        live_text.clear(job.id)


@pytest.mark.asyncio
async def test_idle_stream_sleeps_for_the_db_period(session, monkeypatch):
    token, user, conversation, _ = await stream_seed(session)
    request = StreamRequest(token)
    delays = []

    async def sleep(delay):
        delays.append(delay)
        request.disconnected = True

    monkeypatch.setattr(streams.asyncio, "sleep", sleep)
    response = await streams.stream_conversation(
        conversation.id, request, session, CurrentUser(user_id=user.id, role=user.role),
    )
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)
    assert any("event: conversation\n" in chunk for chunk in chunks)
    assert delays == [streams._DB_POLL_SECONDS]


@pytest.mark.asyncio
async def test_latest_snapshot_and_cursor_pages_cover_complete_history(session):
    user = User(email=f"{uuid4().hex}@example.com", display_name="History",
                password_hash="not-a-login-hash")
    session.add(user)
    await session.flush()
    conversation = Conversation(user_id=user.id, title="History")
    session.add(conversation)
    await session.flush()
    base = utc_now() - timedelta(hours=1)
    rows = [Message(id=UUID(int=index + 1), conversation_id=conversation.id,
                    user_id=user.id, role="user", content=f"message {index}",
                    created_at=base + timedelta(seconds=index // 2))
            for index in range(120)]
    session.add_all(rows)
    await session.commit()
    current = CurrentUser(user_id=user.id, role=user.role)

    snapshot = await conversations.snapshot(session, current, conversation.id)
    assert snapshot.has_more_messages is True
    assert len(snapshot.messages) == 50
    assert [item.id for item in snapshot.messages] == [row.id for row in rows[-50:]]

    recent = await conversations.list_messages(
        session, current, conversation.id, cursor=snapshot.messages[0].id, limit=50,
    )
    assert recent.total == 120
    assert [item.id for item in recent.items] == [row.id for row in rows[20:70]]
    assert recent.next_cursor == recent.items[0].id
    oldest = await conversations.list_messages(
        session, current, conversation.id, cursor=recent.next_cursor, limit=50,
    )
    assert oldest.total == 120 and oldest.next_cursor is None
    assert [item.id for item in oldest.items] == [row.id for row in rows[:20]]
    recovered = [*oldest.items, *recent.items, *snapshot.messages]
    assert [item.id for item in recovered] == [row.id for row in rows]
    assert len({item.id for item in recovered}) == 120

    with pytest.raises(DomainError) as denied:
        await conversations.list_messages(
            session, CurrentUser(user_id=uuid4()), conversation.id,
            cursor=snapshot.messages[0].id, limit=50,
        )
    assert denied.value.code == "not_found"

    other = Conversation(user_id=user.id, title="Other")
    session.add(other)
    await session.flush()
    foreign_cursor = Message(conversation_id=other.id, user_id=user.id,
                             role="user", content="other")
    session.add(foreign_cursor)
    await session.commit()
    with pytest.raises(DomainError) as invalid_cursor:
        await conversations.list_messages(
            session, current, conversation.id, cursor=foreign_cursor.id, limit=50,
        )
    assert invalid_cursor.value.code == "not_found"
