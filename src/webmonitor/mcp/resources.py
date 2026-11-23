"""Read-only MCP resources exposing schemas and live workspace state."""
import json

from mcp.server.mcpserver import MCPServer

from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.mcp.auth import require_principal
from webmonitor.mcp.errors import parse_uuid
from webmonitor.mcp.instructions import delivery_settings_guide, monitor_spec_guide
from webmonitor.services import conversations, drafts, events, monitors, notifications, templates


def register_resources(mcp: MCPServer) -> None:
    @mcp.resource("webmonitor://schemas/monitor-spec", mime_type="application/json")
    async def monitor_spec_schema() -> str:
        require_principal("read")
        return monitor_spec_guide()

    @mcp.resource("webmonitor://schemas/delivery-settings", mime_type="application/json")
    async def delivery_settings_schema() -> str:
        require_principal("read")
        return delivery_settings_guide()

    @mcp.resource("webmonitor://monitors", mime_type="application/json")
    async def monitors_resource() -> str:
        principal = require_principal("read")
        async with get_session_factory()() as session:
            page = await monitors.list_monitors(session, principal.user, 50, 0, archived=False)
            return json.dumps(page.model_dump(mode="json"), ensure_ascii=False)

    @mcp.resource("webmonitor://monitors/{monitor_id}", mime_type="application/json")
    async def monitor_detail_resource(monitor_id: str) -> str:
        principal = require_principal("read")
        mid = parse_uuid(monitor_id, field="monitor_id")
        async with get_session_factory()() as session:
            detail = await monitors.read_monitor(session, principal.user, mid)
            return json.dumps(detail.model_dump(mode="json"), ensure_ascii=False)

    @mcp.resource("webmonitor://monitors/{monitor_id}/latest-snapshot", mime_type="application/json")
    async def monitor_latest_snapshot_resource(monitor_id: str) -> str:
        principal = require_principal("read")
        mid = parse_uuid(monitor_id, field="monitor_id")
        async with get_session_factory()() as session:
            page = await monitors.list_snapshots(session, principal.user, mid, 1, 0)
            if not page.items:
                raise DomainError("not_found", 404, "Monitor has no snapshots yet")
            detail = await monitors.read_snapshot(session, principal.user, page.items[0].id)
            return json.dumps(
                {**detail.model_dump(mode="json"), "untrusted_page_data": True},
                ensure_ascii=False,
            )

    @mcp.resource("webmonitor://events/unacknowledged", mime_type="application/json")
    async def unacknowledged_events_resource() -> str:
        principal = require_principal("read")
        async with get_session_factory()() as session:
            page = await events.list_events(
                session, principal.user, limit=50, offset=0, acknowledged=False
            )
            return json.dumps(page.model_dump(mode="json"), ensure_ascii=False)

    @mcp.resource("webmonitor://drafts/{draft_id}", mime_type="application/json")
    async def draft_resource(draft_id: str) -> str:
        principal = require_principal("read")
        did = parse_uuid(draft_id, field="draft_id")
        async with get_session_factory()() as session:
            draft = await drafts.require_draft(session, principal.user, did)
            view = conversations.draft_view(draft, principal.user)
            return json.dumps(view.model_dump(mode="json"), ensure_ascii=False)

    @mcp.resource("webmonitor://notification-groups", mime_type="application/json")
    async def notification_groups_resource() -> str:
        principal = require_principal("read")
        async with get_session_factory()() as session:
            page = await notifications.list_groups(
                session, 50, 0, include_members=principal.user.role == "admin"
            )
            return json.dumps(page.model_dump(mode="json"), ensure_ascii=False)

    @mcp.resource("webmonitor://email-templates", mime_type="application/json")
    async def email_templates_resource() -> str:
        require_principal("read")
        async with get_session_factory()() as session:
            page = await templates.list_templates(session, 50, 0)
            return json.dumps(page.model_dump(mode="json"), ensure_ascii=False)
