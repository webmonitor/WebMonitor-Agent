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
                 "/api/v1/deliveries", "/api/v1/auth/me"):
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
                 "/api/v1/notification-groups", "/api/v1/deliveries", "/api/v1/members"):
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
    draft = Draft(user_id=user.id, conversation_id=conversation.id,
        spec=_editable_spec(), spec_revision=1, settings_revision=1,
        extraction_preview={"preview_id": "p-1", "spec_revision": 1,
                            "spec_hash": "a" * 64, "extracted_data": {},
                            "coverage": {}, "evidence_refs": [], "warnings": [],
                            "rule_simulation": {},
                            "created_at": "2026-01-01T00:00:00+00:00",
                            "expires_at": "2036-01-01T00:00:00+00:00"})
    session.add(draft)
    await session.commit()

    view = (await client.get(f"/api/v1/drafts/{draft.id}")).json()
    assert view["spec_revision"] == 1 and view["settings_revision"] == 1
    assert view["extraction_preview"]["spec_revision"] == 1
    assert view["delivery_preview"] is None

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


@pytest.mark.asyncio
async def test_template_generation_returns_a_proposal_without_saving(client, session, monkeypatch):
    from webmonitor.agent.template_draft import Proposal
    from webmonitor.errors import DomainError
    from webmonitor.schemas.templates import EmailTemplateConfig
    from webmonitor.services import templates as templates_service

    await ensure_admin(session)
    # Signed out: a valid CSRF token alone does not authorize generation.
    signed_out = {"X-CSRF-Token": (await client.get("/api/v1/auth/csrf")).json()["csrf_token"],
                  "Origin": get_settings().app_origin}
    anonymous = await client.post("/api/v1/email-templates/generate",
        headers=signed_out, json={"description": "一句话"})
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "unauthenticated"

    headers = await sign_in(client)
    proposal = Proposal(
        name="Plain alert",
        config=EmailTemplateConfig.model_validate({
            "subject": "{monitor_name} · {event_label}",
            "blocks": [{"type": "summary"}, {"type": "all_fields"}],
        }))
    calls: list[str] = []

    async def fake_draft(description: str, *, user):
        calls.append(description)
        return proposal

    monkeypatch.setattr(templates_service, "draft", fake_draft)

    response = await client.post("/api/v1/email-templates/generate", headers=headers,
                                 json={"description": "  语气平实，列出全部内容  "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Plain alert"
    assert body["config"]["subject"] == "{monitor_name} · {event_label}"
    assert calls == ["语气平实，列出全部内容"]
    # A proposal is not a stored template.
    assert (await client.get("/api/v1/email-templates")).json()["total"] == 0

    blank = await client.post("/api/v1/email-templates/generate", headers=headers,
                              json={"description": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "validation_failed"

    async def unavailable(description: str, *, user):
        raise DomainError("model_unavailable", 503)

    monkeypatch.setattr(templates_service, "draft", unavailable)
    failed = await client.post("/api/v1/email-templates/generate", headers=headers,
                               json={"description": "一句话"})
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "model_unavailable"




@pytest.mark.asyncio
async def test_email_templates_are_reusable_and_validated(client, session):
    await ensure_admin(session)
    headers = await sign_in(client)
    config = {"subject": "{monitor_name} · {event_label}",
              "blocks": [{"type": "field", "field": "page_title", "emphasis": True},
                         {"type": "evidence_link"}]}

    created = await client.post("/api/v1/email-templates", headers=headers,
        json={"name": f"Design {uuid4().hex[:8]}", "description": "Price mail",
              "config": config})
    assert created.status_code == 201, created.text
    template = created.json()
    assert template["config"]["blocks"][0]["type"] == "field"

    duplicate = await client.post("/api/v1/email-templates", headers=headers,
        json={"name": template["name"], "description": "", "config": config})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "template_name_conflict"

    invalid = await client.post("/api/v1/email-templates", headers=headers,
        json={"name": f"Bad {uuid4().hex[:8]}", "config": {
            "subject": "{unknown_token}", "blocks": []}})
    assert invalid.status_code == 422

    listed = await client.get("/api/v1/email-templates")
    assert [row["id"] for row in listed.json()["items"]] == [template["id"]]

    preview = await client.post("/api/v1/email-templates/preview", headers=headers,
                                json=config)
    assert preview.status_code == 200, preview.text
    emails = preview.json()["rendered_emails"]
    assert [item["event_type"] for item in emails] == [
        "content_changed", "list_changed", "recovered", "run_failed"]
    assert all(item["preview_html"].startswith("<!doctype html>") for item in emails)

    patched = await client.patch(f"/api/v1/email-templates/{template['id']}",
        headers=headers, json={"description": "Updated"})
    assert patched.status_code == 200 and patched.json()["description"] == "Updated"

    removed = await client.delete(f"/api/v1/email-templates/{template['id']}", headers=headers)
    assert removed.status_code == 200
    assert (await client.get("/api/v1/email-templates")).json()["total"] == 0
    missing = await client.delete(f"/api/v1/email-templates/{template['id']}", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "template_not_found"


def _editable_spec() -> dict:
    return {
        "name": "Notice watch",
        "url": "https://8.8.8.8/notice",
        "collection_mode": "http",
        "fields": [{"name": "page_title", "type": "text", "semantic": "Page title",
                    "selector": "h1"}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "text_changed", "field": "page_title"}]},
        "coverage": {"scope": "full", "description": "Page title"},
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
    draft = Draft(user_id=user.id, conversation_id=conversation.id, spec_revision=1,
                  settings_revision=1, spec=_editable_spec(), spec_hash="a" * 64)
    session.add(draft)
    await session.commit()

    edited = {**_editable_spec(), "name": "Notice watch edited"}
    stale = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
                             json={"spec_revision": 2, "spec": edited})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_revision"

    invalid = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
        json={"spec_revision": 1, "spec": {**_editable_spec(), "fields": []}})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_failed"

    missing_revision = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
                                        json={"spec": edited})
    assert missing_revision.status_code == 422

    agent_fields = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
        json={"spec_revision": 1, "spec": {**edited,
              "notification_group_ids": [str(group.id)]}})
    assert agent_fields.status_code == 422

    response = await client.put(f"/api/v1/drafts/{draft.id}", headers=headers,
                                json={"spec_revision": 1, "spec": edited})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["spec_revision"] == 2
    assert body["settings_revision"] == 1
    assert body["spec"]["name"] == "Notice watch edited"
    assert body["extraction_preview"] is None and body["delivery_preview"] is None


def _monitor_spec() -> dict:
    return {
        "name": "History watch",
        "url": "https://8.8.8.8/notice",
        "collection_mode": "http",
        "fields": [{"name": "page_title", "type": "text", "semantic": "Page title",
                    "selector": "h1"}],
        "change_rules": {"mode": "any", "rules": [
            {"type": "text_changed", "field": "page_title"}]},
        "coverage": {"scope": "full", "description": "Page title"},
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
    spec = _monitor_spec()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, spec_revision=1,
                  settings_revision=1, status="published", spec=spec,
                  spec_hash=content_hash(spec), published_spec_version=1,
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
        final_url=spec["url"], extracted_data={"page_title": "Semester notices"},
        coverage={"scope": "full", "description": "Page title"},
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
    assert detail.json()["extracted_data"]["page_title"] == "Semester notices"

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
    from webmonitor.models import Delivery, Event, utc_now

    user = await ensure_admin(session)
    headers = await sign_in(client)
    monitor, _, snapshot, job = await _seed_monitor(session, user)
    session.add(Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                      type="content_changed", change={}))
    failed = Event(monitor_id=monitor.id, job_id=job.id, type="run_failed", change={})
    session.add(failed)
    await session.flush()
    delivery = Delivery(user_id=user.id, monitor_id=monitor.id, event_id=failed.id,
        recipient="ops@example.com", subject="Alert", html="<p>x</p>", body_text="x",
        payload={}, message_id="m-1", available_at=utc_now())
    session.add(delivery)
    await session.commit()

    filtered = await client.get(f"/api/v1/events?event_type=run_failed")
    assert filtered.status_code == 200
    assert [row["type"] for row in filtered.json()["items"]] == ["run_failed"]

    deliveries = (await client.get("/api/v1/deliveries")).json()
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
    draft = Draft(user_id=user.id, conversation_id=conversation.id,
        spec=_editable_spec(), spec_revision=1, settings_revision=1,
        extraction_preview={"preview_id": "p-1", "spec_revision": 1,
                 "spec_hash": "a" * 64, "extracted_data": {},
                 "coverage": {},
                 "evidence_refs": [{"kind": "html", "bucket": "evidence",
                                    "object_key": "page", "size_bytes": 24,
                                    "content_type": "text/html; charset=utf-8",
                                    "sha256": "c" * 64}],
                 "warnings": [],
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


@pytest.mark.asyncio
async def test_an_event_without_mail_reports_why(client, session):
    from webmonitor.models import Event, utc_now

    user = await ensure_admin(session)
    await sign_in(client)
    monitor, _, snapshot, job = await _seed_monitor(session, user)
    skipped = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                    type="content_changed", change={},
                    payload={"skipped": "notification_recipients_empty"})
    session.add(skipped)
    await session.commit()

    row = (await client.get("/api/v1/events")).json()["items"][0]
    assert row["notifications_skipped"] == "notification_recipients_empty"


@pytest.mark.asyncio
async def test_events_and_deliveries_filter_on_state(client, session):
    from webmonitor.models import Delivery, Event, Job, utc_now

    user = await ensure_admin(session)
    await sign_in(client)
    monitor, _, snapshot, job = await _seed_monitor(session, user)
    read = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                 type="content_changed", change={}, acknowledged_at=utc_now())
    other_job = Job(user_id=user.id, kind="production", status="succeeded",
                    monitor_id=monitor.id, revision=1)
    session.add_all([read, other_job])
    await session.flush()
    unread = Event(monitor_id=monitor.id, job_id=other_job.id, type="content_changed", change={})
    session.add(unread)
    await session.flush()
    for event, status in ((read, "sent"), (unread, "failed")):
        session.add(Delivery(user_id=user.id, monitor_id=monitor.id, event_id=event.id,
            recipient="ops@example.com", subject="Alert", html="<p>x</p>", body_text="x",
            payload={}, message_id="m", status=status, available_at=utc_now()))
    await session.commit()

    assert (await client.get("/api/v1/events?acknowledged=false")).json()["total"] == 1
    assert (await client.get("/api/v1/events?acknowledged=true")).json()["total"] == 1
    assert (await client.get("/api/v1/events?acknowledged=false&limit=1")).json()["total"] == 1
    assert (await client.get("/api/v1/deliveries?status=failed")).json()["total"] == 1
    assert (await client.get("/api/v1/deliveries?status=sent")).json()["total"] == 1
    assert (await client.get(
        f"/api/v1/deliveries?monitor_id={uuid4()}")).json()["total"] == 0


@pytest.mark.asyncio
async def test_a_failed_delivery_can_be_retried(client, session):
    from webmonitor.models import Delivery, Event, utc_now

    user = await ensure_admin(session)
    headers = await sign_in(client)
    monitor, _, snapshot, job = await _seed_monitor(session, user)
    event = Event(monitor_id=monitor.id, job_id=job.id, snapshot_id=snapshot.id,
                  type="content_changed", change={})
    session.add(event)
    await session.flush()
    delivery = Delivery(user_id=user.id, monitor_id=monitor.id, event_id=event.id,
        recipient="ops@example.com", subject="Alert", html="<p>x</p>", body_text="x",
        payload={}, message_id="m", status="failed", attempt_count=3, error_code="smtp_rejected",
        failed_at=utc_now(), available_at=utc_now())
    session.add(delivery)
    await session.commit()

    retried = await client.post(f"/api/v1/deliveries/{delivery.id}/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    body = retried.json()
    assert body["status"] == "queued"
    assert body["attempt_count"] == 0
    assert body["error_code"] is None

    again = await client.post(f"/api/v1/deliveries/{delivery.id}/retry", headers=headers)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "delivery_not_retryable"


@pytest.mark.asyncio
async def test_an_oversized_request_is_refused_before_parsing(client, session):
    await ensure_admin(session)
    headers = await sign_in(client)
    oversized = "x" * 1_200_000
    response = await client.post("/api/v1/conversations", headers=headers,
                                 json={"title": "t", "message": {"content": oversized,
                                                                 "client_message_id": "c"}})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


@pytest.mark.asyncio
async def test_api_responses_are_never_cached(client):
    response = await client.get("/api/v1/health/live")
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_readiness_reports_a_stopped_worker(database_url, monkeypatch):
    """Readiness is more than a database: nothing is collected if the worker died."""
    import asyncio

    monkeypatch.setenv("WORKERS_ENABLED", "true")
    get_settings.cache_clear()
    from webmonitor.api.app import create_app
    app = create_app()
    # ASGITransport never runs the lifespan, so no worker is started here.
    app.state.worker_task = asyncio.get_running_loop().create_task(asyncio.sleep(0))
    await asyncio.sleep(0)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as live:
        stopped = await live.get("/api/v1/health/ready")
    assert stopped.status_code == 503
    assert stopped.json()["error"]["code"] == "worker_unavailable"

    app.state.worker_task = asyncio.get_running_loop().create_task(asyncio.sleep(60))
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as live:
            assert (await live.get("/api/v1/health/ready")).status_code == 200
    finally:
        app.state.worker_task.cancel()
        get_settings.cache_clear()
