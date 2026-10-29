"""Every route resolves to a real service call and a real response model."""
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from webmonitor.config import get_settings
from webmonitor.models import Conversation, Draft, NotificationGroup, User
from webmonitor.security.csrf import CSRF_COOKIE


@pytest_asyncio.fixture
async def client(monkeypatch, database_url):
    monkeypatch.setenv("WORKERS_ENABLED", "false")
    monkeypatch.setenv("ADMIN_EMAIL", "route-admin@example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "route-admin-password")
    get_settings.cache_clear()
    from webmonitor.api.app import create_app
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as active:
        yield active
    get_settings.cache_clear()


async def sign_in(client) -> dict[str, str]:
    """Issue CSRF, log the administrator in, return the headers writes need."""
    settings = get_settings()
    token = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
    headers = {"X-CSRF-Token": token, "Origin": settings.app_origin}
    response = await client.post("/api/v1/auth/login", headers=headers, json={
        "email": settings.admin_email,
        "password": settings.admin_password.get_secret_value()})
    assert response.status_code == 200, response.text
    return headers


async def ensure_admin(session) -> User:
    from webmonitor.services import accounts
    settings = get_settings()
    user = await session.scalar(select(User).where(User.email == settings.admin_email))
    if user is None:
        user = await accounts.create_user(session, email=settings.admin_email,
            password=settings.admin_password.get_secret_value(), display_name="Admin",
            role="admin")
        await session.commit()
    return user


@pytest.mark.asyncio
async def test_unauthenticated_reads_are_rejected(client):
    for path in ("/api/v1/conversations", "/api/v1/monitors", "/api/v1/events",
                 "/api/v1/email-deliveries", "/api/v1/auth/me"):
        response = await client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_writes_without_csrf_are_rejected(client):
    response = await client.post("/api/v1/auth/login", json={"email": "a@b.c", "password": "x"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_invalid"
    assert CSRF_COOKIE


@pytest.mark.asyncio
async def test_conversation_round_trip_and_every_list(client, session):
    await ensure_admin(session)
    headers = await sign_in(client)
    assert (await client.get("/api/v1/auth/me")).json()["role"] == "admin"

    conversation = (await client.post("/api/v1/conversations", json={"title": "Route"},
        headers=headers)).json()
    assert conversation["title"] == "Route"

    snapshot = (await client.get(f"/api/v1/conversations/{conversation['id']}")).json()
    assert snapshot["messages"] == [] and snapshot["jobs"] == [] and snapshot["drafts"] == []
    assert snapshot["limits"]["message_max_chars"] > 0

    posted = await client.post(f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "监控 https://example.com/", "client_message_id": str(uuid4())},
        headers=headers)
    assert posted.status_code == 202
    job = posted.json()
    assert job["kind"] == "agent" and job["status"] == "queued"

    replay = await client.post(f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "监控 https://example.com/", "client_message_id": str(uuid4())},
        headers=headers)
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "run_in_progress"

    cancelled = await client.post(f"/api/v1/conversations/{conversation['id']}/cancel",
                                  headers=headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"

    detail = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert detail["status"] == "cancelled" and detail["snapshot"] is None
    assert detail["attempts"] == []

    for path in ("/api/v1/conversations", "/api/v1/monitors", "/api/v1/events",
                 "/api/v1/notification-groups", "/api/v1/email-deliveries", "/api/v1/members"):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert "items" in response.json() and "total" in response.json()


@pytest.mark.asyncio
async def test_draft_view_and_missing_evidence_index(client, session):
    user = await ensure_admin(session)
    await sign_in(client)

    conversation = Conversation(user_id=user.id, title="drafts")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, revision=1,
        spec={"url": "https://example.com/"},
        preview={"revision": 1, "spec_hash": "a" * 64, "extracted_data": {},
                 "coverage": {}, "evidence_refs": [], "rendered_emails": [],
                 "recipients": [], "warnings": [], "rule_simulation": {},
                 "created_at": "2026-01-01T00:00:00+00:00",
                 "expires_at": "2036-01-01T00:00:00+00:00"})
    session.add(draft)
    await session.commit()

    view = (await client.get(f"/api/v1/drafts/{draft.id}")).json()
    assert view["revision"] == 1 and view["preview"]["revision"] == 1

    missing = await client.get(f"/api/v1/drafts/{draft.id}/evidence/0")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_group_writes_require_admin(client, session):
    user = await ensure_admin(session)
    headers = await sign_in(client)

    allowed = await client.post("/api/v1/notification-groups",
        json={"name": f"Ops {uuid4().hex}", "members": [{"email": "ops@example.com"}]},
        headers=headers)
    assert allowed.status_code == 201
    assert allowed.json()["members"] == [{"email": "ops@example.com", "active": True}]

    user.role = "member"
    await session.commit()
    denied = await client.post("/api/v1/notification-groups",
        json={"name": f"Other {uuid4().hex}", "members": []}, headers=headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
    assert await session.scalar(select(NotificationGroup).where(
        NotificationGroup.name.startswith("Other "))) is None
