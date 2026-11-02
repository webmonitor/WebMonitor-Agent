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
async def test_first_message_names_the_conversation(client, session):
    await ensure_admin(session)
    headers = await sign_in(client)
    conversation = (await client.post("/api/v1/conversations", json={"title": None},
        headers=headers)).json()
    assert conversation["title"] is None

    await client.post(f"/api/v1/conversations/{conversation['id']}/messages",
        json={"content": "监控 https://example.com/ 的当前价格，下降 10% 时通知我",
              "client_message_id": str(uuid4())}, headers=headers)
    snapshot = (await client.get(f"/api/v1/conversations/{conversation['id']}")).json()
    assert snapshot["conversation"]["title"] == "监控 https://example.com/ 的当前价格，下降 10% 时通知我"

    named = (await client.post("/api/v1/conversations", json={"title": "我自己命名"},
        headers=headers)).json()
    await client.post(f"/api/v1/conversations/{named['id']}/messages",
        json={"content": "另一段描述", "client_message_id": str(uuid4())}, headers=headers)
    again = (await client.get(f"/api/v1/conversations/{named['id']}")).json()
    assert again["conversation"]["title"] == "我自己命名"


@pytest.mark.asyncio
async def test_creating_a_conversation_can_carry_the_first_message(client, session):
    await ensure_admin(session)
    headers = await sign_in(client)
    before = (await client.get("/api/v1/conversations")).json()["total"]

    created = await client.post("/api/v1/conversations", headers=headers, json={
        "title": None,
        "message": {"content": "监控 https://example.com/ 的库存",
                    "client_message_id": str(uuid4())}})
    assert created.status_code == 201, created.text
    conversation = created.json()
    assert conversation["title"] == "监控 https://example.com/ 的库存"

    snapshot = (await client.get(f"/api/v1/conversations/{conversation['id']}")).json()
    assert [row["content"] for row in snapshot["messages"]] == ["监控 https://example.com/ 的库存"]
    assert [job["kind"] for job in snapshot["jobs"]] == ["agent"]
    assert snapshot["jobs"][0]["status"] == "queued"

    rejected = await client.post("/api/v1/conversations", headers=headers, json={
        "message": {"content": "   ", "client_message_id": str(uuid4())}})
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "message_empty"
    assert (await client.get("/api/v1/conversations")).json()["total"] == before + 1


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


def _editable_spec(group_id) -> dict:
    return {
        "name": "Price watch",
        "url": "https://8.8.8.8/product",
        "collection_mode": "http",
        "fields": [{"name": "current_price", "type": "money", "semantic": "Price",
                    "selector": ".price",
                    "normalize": {"decimal_separator": ".", "currency": "USD"}}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "number_percent_change", "field": "current_price",
             "operator": "decrease_gte", "value": 10}]},
        "schedule": {"interval_seconds": 60, "timezone": "UTC"},
        "notification_group_ids": [str(group_id)],
        "coverage": {"scope": "full", "description": "Single price element"},
    }


@pytest.mark.asyncio
async def test_direct_draft_edit_over_http(client, session):
    user = await ensure_admin(session)
    headers = await sign_in(client)
    group = NotificationGroup(name=f"Edit {uuid4().hex}",
        members=[{"email": "ops@example.com", "active": True}],
        created_by_user_id=user.id)
    conversation = Conversation(user_id=user.id, title="Direct edit")
    session.add_all([group, conversation])
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, revision=1,
                  spec=_editable_spec(group.id), spec_hash="a" * 64)
    session.add(draft)
    await session.commit()

    edited = {**_editable_spec(group.id), "name": "Price watch edited"}
    stale = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
                             json={"revision": 2, "spec": edited})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"

    invalid = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
        json={"revision": 1, "spec": {**_editable_spec(group.id), "fields": []}})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_failed"

    response = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
                                json={"revision": 1, "spec": edited})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 2
    assert body["spec"]["name"] == "Price watch edited"
    assert body["preview"] is None and body["preview_hash"] is None


def _monitor_spec(group_id) -> dict:
    return {
        "name": "History watch",
        "url": "https://8.8.8.8/product",
        "collection_mode": "http",
        "fields": [{"name": "current_price", "type": "money", "semantic": "Price",
                    "selector": ".price",
                    "normalize": {"decimal_separator": ".", "currency": "USD"}}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "number_percent_change", "field": "current_price",
             "operator": "decrease_gte", "value": 10}]},
        "schedule": {"interval_seconds": 60, "timezone": "UTC"},
        "notification_group_ids": [str(group_id)],
        "coverage": {"scope": "full", "description": "Single price element"},
    }


async def _seed_monitor(session, user):
    from webmonitor.models import Job, Monitor, Snapshot, utc_now
    from webmonitor.schemas.monitors import content_hash

    group = NotificationGroup(name=f"History {uuid4().hex}",
        members=[{"email": "ops@example.com", "active": True}],
        created_by_user_id=user.id)
    conversation = Conversation(user_id=user.id, title="History")
    session.add_all([group, conversation])
    await session.flush()
    spec = _monitor_spec(group.id)
    draft = Draft(user_id=user.id, conversation_id=conversation.id, revision=1,
                  status="published", spec=spec, spec_hash=content_hash(spec),
                  monitor_id=None)
    session.add(draft)
    await session.flush()
    monitor = Monitor(user_id=user.id, draft_id=draft.id, name=spec["name"],
        url=spec["url"], status="active", spec=spec, spec_version=1,
        spec_hash=draft.spec_hash, collection_mode="http", interval_seconds=60,
        timezone="UTC", notification_group_ids=[str(group.id)],
        approved_recipients=[{"email": "ops@example.com", "group_ids": [str(group.id)]}],
        baseline_status="pending_first_success", rule_state={}, next_run_at=utc_now())
    session.add(monitor)
    await session.flush()
    draft.monitor_id = monitor.id
    job = Job(user_id=user.id, kind="production", status="succeeded",
              monitor_id=monitor.id, revision=1)
    session.add(job)
    await session.flush()
    snapshot = Snapshot(monitor_id=monitor.id, job_id=job.id, spec_version=1,
        final_url=spec["url"], extracted_data={"current_price": 100},
        coverage={"scope": "full", "description": "Single price element"},
        rule_state={}, evidence_refs=[], collected_at=utc_now())
    session.add(snapshot)
    await session.flush()
    return monitor, group, snapshot, job


@pytest.mark.asyncio
async def test_monitor_history_lifecycle_over_http(client, session):
    user = await ensure_admin(session)
    headers = await sign_in(client)
    monitor, _, snapshot, _ = await _seed_monitor(session, user)
    await session.commit()

    snapshots = await client.get(f"/api/v1/monitors/{monitor.id}/snapshots")
    assert snapshots.status_code == 200
    assert [row["id"] for row in snapshots.json()["items"]] == [str(snapshot.id)]

    detail = await client.get(f"/api/v1/snapshots/{snapshot.id}")
    assert detail.status_code == 200
    assert detail.json()["monitor_name"] == monitor.name
    assert detail.json()["extracted_data"]["current_price"] == 100

    versions = await client.get(f"/api/v1/monitors/{monitor.id}/specs")
    assert versions.status_code == 200
    assert versions.json()["items"][0]["current"] is True

    renamed = await client.patch(f"/api/v1/monitors/{monitor.id}",
        json={"name": "Renamed watch"}, headers=headers)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed watch"
    detail = (await client.get(f"/api/v1/monitors/{monitor.id}")).json()
    assert detail["spec"]["name"] == "Renamed watch"
    assert detail["approved_recipients"] == ["ops@example.com"]

    archived = await client.post(f"/api/v1/monitors/{monitor.id}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert (await client.get("/api/v1/monitors")).json()["total"] == 0
    archived_list = (await client.get("/api/v1/monitors?archived=true")).json()
    assert [row["id"] for row in archived_list["items"]] == [str(monitor.id)]

    restored = await client.post(f"/api/v1/monitors/{monitor.id}/restore", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert (await client.get("/api/v1/monitors")).json()["total"] == 1


@pytest.mark.asyncio
async def test_events_filter_and_delivery_monitor_name(client, session):
    from webmonitor.models import EmailDelivery, Event, utc_now

    user = await ensure_admin(session)
    headers = await sign_in(client)
    monitor, _, snapshot, job = await _seed_monitor(session, user)
    session.add(Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                      type="price_changed", change={}))
    failed = Event(monitor_id=monitor.id, job_id=job.id, type="run_failed", change={})
    session.add(failed)
    await session.flush()
    delivery = EmailDelivery(user_id=user.id, monitor_id=monitor.id, event_id=failed.id,
        recipient="ops@example.com", subject="Alert", html="<p>x</p>", body_text="x",
        payload={}, message_id="m-1", available_at=utc_now())
    session.add(delivery)
    await session.commit()

    filtered = await client.get(f"/api/v1/events?event_type=run_failed")
    assert filtered.status_code == 200
    assert [row["type"] for row in filtered.json()["items"]] == ["run_failed"]

    deliveries = (await client.get("/api/v1/email-deliveries")).json()
    assert deliveries["items"][0]["monitor_name"] == monitor.name


@pytest.mark.asyncio
async def test_invitations_require_admin_and_issue_a_link(client, session):
    user = await ensure_admin(session)
    headers = await sign_in(client)

    created = await client.post("/api/v1/members/invitations", headers=headers,
        json={"email": "new-member@example.com", "ttl_hours": 12})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["url"].startswith(get_settings().app_origin + "/register?")
    assert "invitation_token=" in body["url"]

    pending = await client.get("/api/v1/members/invitations")
    assert pending.status_code == 200
    assert [row["email"] for row in pending.json()["items"]] == ["new-member@example.com"]

    user.role = "member"
    await session.commit()
    denied = await client.post("/api/v1/members/invitations", headers=headers,
        json={"email": "another@example.com", "ttl_hours": 12})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
    assert (await client.get("/api/v1/members/invitations")).status_code == 403


@pytest.mark.asyncio
async def test_html_evidence_downloads_with_an_html_filename(client, session, monkeypatch):
    from webmonitor.api.routes import evidence as evidence_route

    user = await ensure_admin(session)
    await sign_in(client)
    conversation = Conversation(user_id=user.id, title="archive")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, revision=1,
        spec={"url": "https://example.com/"},
        preview={"revision": 1, "spec_hash": "a" * 64, "extracted_data": {},
                 "coverage": {},
                 "evidence_refs": [{"kind": "html", "bucket": "evidence",
                                    "object_key": "page", "size_bytes": 24,
                                    "content_type": "text/html; charset=utf-8",
                                    "sha256": "c" * 64}],
                 "rendered_emails": [], "recipients": [], "warnings": [],
                 "rule_simulation": {}, "created_at": "2026-01-01T00:00:00+00:00",
                 "expires_at": "2036-01-01T00:00:00+00:00"})
    session.add(draft)
    await session.commit()

    async def chunks():
        yield b"<html>archived page</html>"

    async def fake_stream(bucket, key):
        assert (bucket, key) == ("evidence", "page")
        return chunks()

    monkeypatch.setattr(evidence_route, "stream_evidence", fake_stream)
    response = await client.get(f"/api/v1/drafts/{draft.id}/evidence/0")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == \
        'attachment; filename="cccccccccccccccc.html"'
    assert response.text == "<html>archived page</html>"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_conversations_archive_restore_and_message(client, session):
    await ensure_admin(session)
    headers = await sign_in(client)
    keep = await client.post("/api/v1/conversations", headers=headers, json={"title": "Keep open"})
    archive = await client.post("/api/v1/conversations", headers=headers, json={"title": "Archive me"})
    assert keep.status_code == 201 and archive.status_code == 201
    keep_id, archive_id = keep.json()["id"], archive.json()["id"]

    assert (await client.post(f"/api/v1/conversations/{archive_id}/archive",
                              headers=headers)).status_code == 200
    listed = await client.get("/api/v1/conversations")
    assert [item["id"] for item in listed.json()["items"]] == [keep_id]
    hidden = await client.get("/api/v1/conversations?archived=true")
    assert [item["id"] for item in hidden.json()["items"]] == [archive_id]

    # Writing into an archived conversation brings it back to the sidebar.
    posted = await client.post(f"/api/v1/conversations/{archive_id}/messages", headers=headers,
        json={"content": "继续", "client_message_id": str(uuid4())})
    assert posted.status_code == 202
    listed = await client.get("/api/v1/conversations")
    assert archive_id in [item["id"] for item in listed.json()["items"]]

    assert (await client.post(f"/api/v1/conversations/{archive_id}/archive",
                              headers=headers)).status_code == 200
    assert (await client.post(f"/api/v1/conversations/{archive_id}/restore",
                              headers=headers)).status_code == 200
    assert (await client.get("/api/v1/conversations?archived=true")).json()["items"] == []
