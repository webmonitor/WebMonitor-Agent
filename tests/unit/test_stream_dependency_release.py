"""Streaming responses release request ORM state before their bodies begin."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from webmonitor.api.routes import evidence, streams
from webmonitor.security.auth import CurrentUser


class ClosableSession:
    def __init__(self, values=()):
        self.values = list(values)
        self.closed = False

    async def get(self, *args, **kwargs):
        return self.values.pop(0)

    async def close(self):
        self.closed = True


class Request:
    cookies = {"wm_session": "raw-session"}
    headers = {}


@pytest.mark.asyncio
async def test_conversation_response_closes_the_request_session_before_returning(monkeypatch):
    session = ClosableSession()
    user = CurrentUser(user_id=uuid4())

    async def require_conversation(active, current, conversation_id):
        assert active is session and current is user
        assert not session.closed

    monkeypatch.setattr(streams.conversations, "require_conversation", require_conversation)
    response = await streams.stream_conversation(uuid4(), Request(), session, user)
    assert session.closed
    await response.body_iterator.aclose()


@pytest.mark.asyncio
async def test_snapshot_evidence_detaches_references_before_closing(monkeypatch):
    user_id = uuid4()
    monitor_id = uuid4()
    reference = {"bucket": "evidence", "object_key": "committed/object"}
    session = ClosableSession([
        SimpleNamespace(monitor_id=monitor_id, evidence_refs=[reference]),
        SimpleNamespace(user_id=user_id),
    ])
    returned = object()

    async def response(value):
        assert session.closed
        assert value == reference and value is not reference
        return returned

    monkeypatch.setattr(evidence, "_response", response)
    result = await evidence.snapshot_evidence(
        uuid4(), 0, session, CurrentUser(user_id=user_id)
    )
    assert session.closed and result is returned


@pytest.mark.asyncio
async def test_draft_evidence_detaches_references_before_closing(monkeypatch):
    reference = {"bucket": "evidence", "object_key": "preview/object"}
    session = ClosableSession()
    returned = object()

    async def require_draft(active, user, draft_id):
        return SimpleNamespace(extraction_preview={"evidence_refs": [reference]})

    async def response(value):
        assert session.closed
        assert value == reference and value is not reference
        return returned

    monkeypatch.setattr(evidence.drafts, "require_draft", require_draft)
    monkeypatch.setattr(evidence, "_response", response)
    result = await evidence.draft_evidence(
        uuid4(), 0, session, CurrentUser(user_id=uuid4())
    )
    assert session.closed and result is returned
