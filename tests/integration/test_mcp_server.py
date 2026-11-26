"""End-to-end integration tests for Streamable HTTP MCP server, PAT auth and Mode 2 flow."""
import asyncio
import contextlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

import httpx2
import pytest
import pytest_asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from sqlalchemy import select

from tests.integration.support import NOTICE_SPEC, collection_result, seed_owner
from webmonitor import worker
from webmonitor.config import get_settings
from webmonitor.models import ApiToken, Conversation, Draft, Event, Job, User, utc_now
from webmonitor.security.auth import CurrentUser
from webmonitor.services import accounts, jobs, tokens


@contextlib.asynccontextmanager
async def running_app(app):
    """Hold the lifespan in one task, as the MCP SDK's cancel scopes require."""
    ready = asyncio.Event()
    stop = asyncio.Event()

    async def manage():
        async with app.router.lifespan_context(app):
            ready.set()
            await stop.wait()

    task = asyncio.create_task(manage())
    ready_waiter = asyncio.create_task(ready.wait())
    await asyncio.wait({task, ready_waiter}, return_when=asyncio.FIRST_COMPLETED)
    if not ready.is_set():
        ready_waiter.cancel()
        await task
        raise RuntimeError("Application lifespan exited during startup")
    try:
        yield app
    finally:
        stop.set()
        await task


@pytest_asyncio.fixture
async def mcp_app(monkeypatch, database_url):
    monkeypatch.setenv("WORKERS_ENABLED", "false")
    monkeypatch.setenv("MCP_ENABLED", "true")
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:8080")
    monkeypatch.setenv("TARGET_POLICY", "public")
    get_settings.cache_clear()
    from webmonitor.api.app import create_app

    async with running_app(create_app()) as app:
        yield app
    get_settings.cache_clear()


@contextlib.asynccontextmanager
async def open_mcp_session(app, token: str):
    http_client = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    async with http_client:
        async with streamable_http_client("http://testserver/mcp", http_client=http_client) as (
            read_stream,
            write_stream,
        ):
            async with ClientSession(read_stream, write_stream) as mcp_session:
                init_result = await mcp_session.initialize()
                yield mcp_session, init_result


def _tool_json(result) -> dict:
    assert result.content, result
    return json.loads(result.content[0].text)


@pytest.mark.asyncio
async def test_mcp_disabled_by_default_returns_404(monkeypatch, database_url):
    monkeypatch.setenv("WORKERS_ENABLED", "false")
    monkeypatch.setenv("MCP_ENABLED", "false")
    get_settings.cache_clear()
    from webmonitor.api.app import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            res = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            assert res.status_code == 404
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mcp_auth_origin_cookie_and_token_lifecycle(mcp_app, session):
    admin, current_admin, _ = await seed_owner(session)
    admin.password_hash = await accounts._hash("correct horse battery")
    await session.commit()

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=mcp_app), base_url="http://testserver"
    ) as client:
        # 1. Missing Bearer token -> 401
        no_auth = await client.post("/mcp", json={})
        assert no_auth.status_code == 401
        assert no_auth.json()["error"]["code"] == "unauthenticated"

        # 2. Sign in with browser session cookie; cookie alone must NOT authenticate /mcp
        csrf_token = (await client.get("/api/v1/auth/csrf")).json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf_token, "Origin": get_settings().app_origin}
        login = await client.post(
            "/api/v1/auth/login",
            headers=headers,
            json={"email": admin.email, "password": "correct horse battery"},
        )
        assert login.status_code == 200

        cookie_only = await client.post("/mcp", json={})
        assert cookie_only.status_code == 401
        assert cookie_only.json()["error"]["code"] == "unauthenticated"

        # 3. Create PAT via REST API (cookie + CSRF protected)
        created = await client.post(
            "/api/v1/tokens",
            headers=headers,
            json={"name": "Claude local", "ttl_days": 30},
        )
        assert created.status_code == 201, created.text
        created_body = created.json()
        raw_pat = created_body["token"]
        assert raw_pat.startswith("wm_pat_")
        assert created_body["token_prefix"] == raw_pat[:16]
        assert "drafts:approve" not in created_body["scopes"]

        listed = (await client.get("/api/v1/tokens")).json()
        assert listed["total"] == 1
        assert "token" not in listed["items"][0]

        # 4. Disallowed Origin rejected on /mcp even with valid Bearer token
        bad_origin = await client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {raw_pat}", "Origin": "https://evil.example"},
            json={},
        )
        assert bad_origin.status_code == 403
        assert bad_origin.json()["error"]["code"] == "origin_invalid"

        # 5. Revoke token -> 401 on /mcp
        revoked = await client.delete(f"/api/v1/tokens/{created_body['id']}", headers=headers)
        assert revoked.status_code == 200
        assert revoked.json()["revoked_at"] is not None

        after_revoke = await client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {raw_pat}"},
            json={},
        )
        assert after_revoke.status_code == 401

        # 6. Expired token -> 401
        expired_row, expired_raw = await tokens.create_token(
            session, current_admin, name="Expired", scopes=["read"], ttl_days=1
        )
        expired_row.expires_at = utc_now() - timedelta(minutes=1)
        await session.commit()
        after_expire = await client.post(
            "/mcp", headers={"Authorization": f"Bearer {expired_raw}"}, json={}
        )
        assert after_expire.status_code == 401

        # 7. Deactivated user -> 401
        _, live_raw = await tokens.create_token(
            session, current_admin, name="Deactivated check", scopes=["read"], ttl_days=10
        )
        await session.commit()
        await accounts.set_availability(session, admin, False)
        await session.commit()
        after_disable = await client.post(
            "/mcp", headers={"Authorization": f"Bearer {live_raw}"}, json={}
        )
        assert after_disable.status_code == 401
        stored = await session.scalar(select(ApiToken).where(ApiToken.user_id == admin.id))
        assert stored is not None and stored.revoked_at is not None


@pytest.mark.asyncio
async def test_mcp_mode2_end_to_end_discovery_draft_preview_approve_and_ops(
    mcp_app, session, monkeypatch
):
    user, current, group = await seed_owner(session)
    _, limited_token = await tokens.create_token(
        session, current, name="Default limited", scopes=None, ttl_days=30
    )
    _, approve_token = await tokens.create_token(
        session,
        current,
        name="Full approve",
        scopes=["read", "discover", "drafts:write", "drafts:approve", "monitors:write", "events:write"],
        ttl_days=30,
    )
    await session.commit()

    async def fake_probe(url: str, *, transport=None):
        return {
            "url": url,
            "final_url": url,
            "status": 200,
            "content_type": "text/html",
            "bytes": 120,
            "title": "Notice board",
            "text_sample": "Registration Open",
            "markers": {"next_data": False, "next_f": False, "root": False, "app": False, "ld_json": False},
            "comments": [],
            "scripts": [],
            "json_summary": None,
            "json_sample": None,
        }

    async def fake_replay(req, *, transport=None):
        return {
            "status": 200,
            "final_url": req.url,
            "content_type": "application/json",
            "bytes": 42,
            "json_summary": {"keys": ["ok"]},
            "json_sample": '{"ok": true}',
            "text_sample": None,
        }

    async def fake_collect_http(url: str, spec=None, **kwargs):
        from webmonitor.collection.types import CollectionResult

        if spec is None:
            return CollectionResult(
                final_url=url,
                body=None,
                screenshot=None,
                fields={},
                coverage={"scope": "full", "description": "html"},
                duration_ms=1,
                warnings=[],
                analysis={"selectors": ["h1", "li"]},
            )
        res = collection_result(spec)
        return CollectionResult(
            final_url=res["final_url"],
            body=None,
            screenshot=None,
            fields=res["fields"],
            coverage=res["coverage"],
            duration_ms=1,
            warnings=[],
        )

    monkeypatch.setattr(worker, "probe", fake_probe)
    monkeypatch.setattr(worker, "replay", fake_replay)
    monkeypatch.setattr(worker, "collect_http", fake_collect_http)

    # Background worker helper for queued analyze/preview jobs during tool wait
    async def drive_queued_job(kind: str):
        for _ in range(100):
            async with (await _session_ctx())() as worker_session:
                async with worker_session.begin():
                    claimed = await jobs.claim(worker_session, kind=kind, worker_id="test-worker")
                if claimed is not None:
                    await worker._collect(claimed.id, "test-worker")
                    return claimed.id
            await asyncio.sleep(0.02)
        raise AssertionError(f"No {kind} job appeared")

    async def _session_ctx():
        from webmonitor.db import get_session_factory

        return get_session_factory()

    async with open_mcp_session(mcp_app, limited_token) as (mcp_session, init_res):
        assert "Mode 2" in (init_res.instructions or "")

        tool_names = {tool.name for tool in (await mcp_session.list_tools()).tools}
        assert {"probe_target", "analyze_target", "save_monitor_draft", "preview_monitor_draft", "approve_draft"} <= tool_names

        resources = await mcp_session.list_resources()
        assert any(str(item.uri) == "webmonitor://schemas/monitor-spec" for item in resources.resources)
        prompts = await mcp_session.list_prompts()
        assert any(item.name == "create-monitor" for item in prompts.prompts)

        schema_res = await mcp_session.read_resource("webmonitor://schemas/monitor-spec")
        schema_json = json.loads(schema_res.contents[0].text)
        assert "json_schema" in schema_json and "examples" in schema_json

        # 1. probe_target via worker analyze job
        probe_task = asyncio.create_task(
            mcp_session.call_tool("probe_target", {"url": NOTICE_SPEC["url"], "timeout_seconds": 15})
        )
        await drive_queued_job("analyze")
        probe_res = await probe_task
        assert not probe_res.is_error
        probe_data = _tool_json(probe_res)
        assert probe_data["untrusted_page_data"] is True
        assert probe_data["probe"]["title"] == "Notice board"

        # 2. replay_request via worker analyze job
        replay_task = asyncio.create_task(
            mcp_session.call_tool(
                "replay_request",
                {"request": {"method": "GET", "url": "https://8.8.8.8/api/notices"}, "timeout_seconds": 15},
            )
        )
        await drive_queued_job("analyze")
        replay_res = await replay_task
        assert not replay_res.is_error
        assert _tool_json(replay_res)["replay"]["status"] == 200

        # 3. invalid MonitorSpec returns structured validation error without writing DB
        bad_save = await mcp_session.call_tool("save_monitor_draft", {"spec": {"name": "Incomplete"}})
        assert bad_save.is_error is True
        assert _tool_json(bad_save)["error"]["code"] == "validation_failed"
        assert (await session.scalars(select(Draft))).all() == []

        # 4. valid MonitorSpec auto-creates Conversation + Draft
        saved_res = await mcp_session.call_tool("save_monitor_draft", {"spec": NOTICE_SPEC})
        assert not saved_res.is_error
        saved = _tool_json(saved_res)
        assert saved["spec_revision"] == 1
        draft_id = saved["draft_id"]

        # 5. preview_monitor_draft runs real preview pipeline and freezes hashes
        preview_task = asyncio.create_task(
            mcp_session.call_tool(
                "preview_monitor_draft",
                {"draft_id": draft_id, "spec_revision": 1, "wait": True, "timeout_seconds": 15},
            )
        )
        await drive_queued_job("preview")
        preview_res = await preview_task
        assert not preview_res.is_error
        preview_data = _tool_json(preview_res)
        assert preview_data["extracted_data"]["page_title"] == "Semester notices"
        assert preview_data["extraction_preview_hash"]
        assert preview_data["delivery_preview_hash"]
        assert "/app?conversation=" in preview_data["approval_url"]

        # 6. approve_draft refused without drafts:approve scope
        denied_approve = await mcp_session.call_tool(
            "approve_draft",
            {
                "draft_id": draft_id,
                "spec_revision": preview_data["spec_revision"],
                "settings_revision": preview_data["settings_revision"],
                "extraction_preview_hash": preview_data["extraction_preview_hash"],
                "delivery_preview_hash": preview_data["delivery_preview_hash"],
            },
        )
        assert denied_approve.is_error is True
        assert _tool_json(denied_approve)["error"]["code"] == "insufficient_scope"

    # 7. approve_draft succeeds with drafts:approve scope, then run ops tools
    async with open_mcp_session(mcp_app, approve_token) as (mcp_session, _):
        approved_res = await mcp_session.call_tool(
            "approve_draft",
            {
                "draft_id": draft_id,
                "spec_revision": preview_data["spec_revision"],
                "settings_revision": preview_data["settings_revision"],
                "extraction_preview_hash": preview_data["extraction_preview_hash"],
                "delivery_preview_hash": preview_data["delivery_preview_hash"],
            },
        )
        assert not approved_res.is_error
        approved = _tool_json(approved_res)
        monitor_id = approved["monitor_id"]

        monitors_list = _tool_json(await mcp_session.call_tool("list_monitors", {}))
        assert monitors_list["total"] == 1 and monitors_list["items"][0]["id"] == monitor_id

        detail = _tool_json(await mcp_session.call_tool("get_monitor", {"monitor_id": monitor_id}))
        assert detail["id"] == monitor_id

        queued_run = _tool_json(
            await mcp_session.call_tool("run_monitor_now", {"monitor_id": monitor_id, "wait": False})
        )
        assert queued_run["job_id"] and queued_run["status"] == "queued"
        assert "kind" not in queued_run and "result" not in queued_run

        paused = _tool_json(await mcp_session.call_tool("pause_monitor", {"monitor_id": monitor_id}))
        assert paused["status"] == "paused"
        resumed = _tool_json(await mcp_session.call_tool("resume_monitor", {"monitor_id": monitor_id}))
        assert resumed["status"] == "active"

        # Seed an event and acknowledge it via MCP
        job_row = Job(
            user_id=user.id,
            kind="production",
            status="succeeded",
            monitor_id=UUID(monitor_id),
            revision=1,
        )
        session.add(job_row)
        await session.flush()
        event_row = Event(
            monitor_id=UUID(monitor_id),
            job_id=job_row.id,
            type="content_changed",
            change={"summary": "Changed"},
            payload={},
        )
        session.add(event_row)
        await session.commit()

        events_page = _tool_json(
            await mcp_session.call_tool("list_events", {"monitor_id": monitor_id, "acknowledged": False})
        )
        assert events_page["total"] == 1
        acked = _tool_json(
            await mcp_session.call_tool("acknowledge_event", {"event_id": str(event_row.id)})
        )
        assert acked == {"event_id": str(event_row.id), "acknowledged": True}


@pytest.mark.asyncio
async def test_mcp_rbac_isolation_and_member_recipient_redaction(mcp_app, session, monkeypatch):
    admin, admin_current, group = await seed_owner(session)
    member = User(
        email=f"member-{uuid4().hex}@example.com",
        display_name="Member",
        password_hash="not-a-login-hash",
        role="member",
    )
    session.add(member)
    await session.flush()
    member_current = CurrentUser(user_id=member.id, role="member")
    _, member_token = await tokens.create_token(
        session,
        member_current,
        name="Member MCP",
        scopes=["read", "drafts:write"],
        ttl_days=30,
    )

    # Create an admin-owned conversation/draft
    admin_conv = Conversation(user_id=admin.id, title="Admin secret")
    session.add(admin_conv)
    await session.flush()
    from webmonitor.services import drafts
    from tests.integration.support import build_spec

    admin_draft = await drafts.save_spec(
        session, admin_current, conversation_id=admin_conv.id, spec=build_spec("Admin watch")
    )
    # Create a member-owned draft with notification group configured
    member_conv = Conversation(user_id=member.id, title="Member flow")
    session.add(member_conv)
    await session.flush()
    member_draft = await drafts.save_spec(
        session, member_current, conversation_id=member_conv.id, spec=build_spec("Member watch")
    )
    await session.commit()

    async with open_mcp_session(mcp_app, member_token) as (mcp_session, _):
        # Cannot access admin's draft
        foreign = await mcp_session.call_tool(
            "save_monitor_draft",
            {"spec": NOTICE_SPEC, "draft_id": str(admin_draft.id)},
        )
        assert foreign.is_error is True
        assert _tool_json(foreign)["error"]["code"] == "not_found"

        # Notification groups redact member email addresses for non-admins
        groups = _tool_json(await mcp_session.call_tool("list_notification_groups", {}))
        assert groups["total"] == 1
        assert groups["items"][0]["member_count"] == 1
        assert groups["items"][0]["members"] == []

        # Updating draft settings returns redacted delivery preview / settings copy
        updated = _tool_json(
            await mcp_session.call_tool(
                "update_draft_settings",
                {
                    "draft_id": str(member_draft.id),
                    "settings_revision": 0,
                    "settings": {
                        "channel": "email",
                        "notification_group_ids": [str(group.id)],
                        "schedule": {"interval_seconds": 120, "timezone": "UTC"},
                    },
                },
            )
        )
        assert updated["settings_revision"] == 1
