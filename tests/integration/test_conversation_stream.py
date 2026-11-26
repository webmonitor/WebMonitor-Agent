"""The conversation SSE emits complete, replay-safe authenticated snapshots."""
import json
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio

from tests.integration.test_api_routes import ensure_admin
from webmonitor.agent import live_text
from webmonitor.api.routes.streams import stream_conversation
from webmonitor.config import get_settings
from webmonitor.models import Conversation, Job, Session as AuthSession, utc_now
from webmonitor.security.auth import CurrentUser
from webmonitor.services import accounts


@pytest_asyncio.fixture
async def client(monkeypatch, database_url):
    monkeypatch.setenv("WORKERS_ENABLED", "false")
    monkeypatch.setenv("ADMIN_EMAIL", "stream-admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "stream-admin-password")
    get_settings.cache_clear()
    from webmonitor.api.app import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as active:
        yield active
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_conversation_stream_requires_session(client):
    response = await client.get(f"/api/v1/conversations/{__import__('uuid').uuid4()}/stream")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_conversation_stream_emits_complete_snapshot(client, session):
    user = await ensure_admin(session)
    conversation = Conversation(user_id=user.id, title="Live conversation")
    session.add(conversation)
    await session.flush()
    job = Job(user_id=user.id, kind="agent", status="running", conversation_id=conversation.id,
              partial_text="stored")
    session.add(job)
    token = "stream-test-token"
    session.add(AuthSession(user_id=user.id, token_hash=accounts.token_hash(token),
                            expires_at=utc_now() + timedelta(hours=1)))
    await session.commit()
    live_text.append(job.id, " live")

    class ConnectedRequest:
        cookies = {"wm_session": token}
        headers = {}

        async def is_disconnected(self):
            return False

    response = await stream_conversation(
        conversation.id, ConnectedRequest(), session, CurrentUser(user_id=user.id, role="admin")
    )
    event_id = None
    payload = None
    try:
        async for chunk in response.body_iterator:
            for line in chunk.splitlines():
                if line.startswith("id: "):
                    event_id = line.removeprefix("id: ")
                if line.startswith("data: "):
                    payload = json.loads(line.removeprefix("data: "))
            if payload is not None:
                break
    finally:
        await response.body_iterator.aclose()
        live_text.clear(job.id)

    assert event_id and len(event_id) == 64
    assert payload is not None
    assert payload["conversation"]["id"] == str(conversation.id)
    assert payload["conversation"]["title"] == "Live conversation"
    assert payload["messages"] == []
    assert len(payload["jobs"]) == 1
    # Durable snapshots never inherit process-local text; deltas carry it separately.
    assert payload["jobs"][0]["partial_text"] == "stored"
