"""Operational tools for controlling monitors, events and deliveries."""
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.mcp.errors import parse_uuid, run_tool
from webmonitor.mcp.tools_discover import _clamp_timeout, _wait_with_progress
from webmonitor.schemas.api import MonitorRename
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.services import events, monitors, notifications

MUTATE_LOCAL = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

# Write scopes never imply read: mutations acknowledge with IDs and outcomes,
# while monitor, job, event and delivery payloads remain behind the read scope.


def register_ops_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    async def run_monitor_now(
        monitor_id: str,
        wait: bool = False,
        timeout_seconds: int = 60,
        ctx: Context | None = None,
    ) -> CallToolResult:
        """Trigger an immediate production collection job for an active monitor."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                job = await monitors.enqueue_manual(session, principal.user, mid)
                view = {"job_id": str(job.id), "status": job.status}
                await session.commit()
            if not wait:
                return view
            try:
                finished = await _wait_with_progress(
                    job.id,
                    timeout=_clamp_timeout(timeout_seconds),
                    cancel_on_timeout=False,
                    ctx=ctx,
                )
            except DomainError as exc:
                if exc.code == "job_timeout":
                    return {**view, "timed_out": True}
                raise
            # Collection results are readable data, not a monitors:write result.
            return {"job_id": str(finished.id), "status": finished.status}

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def pause_monitor(monitor_id: str) -> CallToolResult:
        """Pause a monitor and cancel any pending collection jobs."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                monitor = await monitors.pause_monitor(session, principal.user, mid)
                result = {"monitor_id": str(mid), "status": monitor.status}
                await session.commit()
                return result

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def resume_monitor(monitor_id: str) -> CallToolResult:
        """Resume a paused, non-archived monitor."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                monitor = await monitors.resume_monitor(session, principal.user, mid)
                result = {"monitor_id": str(mid), "status": monitor.status}
                await session.commit()
                return result

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def rename_monitor(monitor_id: str, name: str) -> CallToolResult:
        """Rename a monitor without bumping its collection contract version."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            body = MonitorRename(name=name)
            async with get_session_factory()() as session:
                await monitors.rename_monitor(session, principal.user, mid, body.name)
                await session.commit()
                return {"monitor_id": str(mid), "renamed": True}

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def archive_monitor(monitor_id: str) -> CallToolResult:
        """Archive a monitor and pause its schedule."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                monitor = await monitors.archive_monitor(session, principal.user, mid)
                result = {"monitor_id": str(mid), "status": monitor.status}
                await session.commit()
                return result

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def restore_monitor(monitor_id: str) -> CallToolResult:
        """Restore an archived monitor (remains paused until resumed)."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                monitor = await monitors.restore_monitor(session, principal.user, mid)
                result = {"monitor_id": str(mid), "status": monitor.status}
                await session.commit()
                return result

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def update_monitor_settings(
        monitor_id: str, settings: dict[str, Any]
    ) -> CallToolResult:
        """Update a live monitor's delivery channel, recipients, schedule or email template."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            parsed = DeliverySettings.model_validate(settings)
            async with get_session_factory()() as session:
                await monitors.update_delivery_settings(session, principal.user, mid, parsed)
                await session.commit()
                # Do not echo the monitor contract, recipients or settings through
                # a token that was granted mutation access without read access.
                return {"monitor_id": str(mid), "updated": True}

        return await run_tool("monitors:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def acknowledge_event(event_id: str) -> CallToolResult:
        """Mark a change or failure event as acknowledged."""

        async def op(principal):
            eid = parse_uuid(event_id, field="event_id")
            async with get_session_factory()() as session:
                await events.acknowledge_event(session, principal.user, eid)
                await session.commit()
                return {"event_id": str(eid), "acknowledged": True}

        return await run_tool("events:write", op)

    @mcp.tool(annotations=MUTATE_LOCAL)
    async def retry_delivery(delivery_id: str) -> CallToolResult:
        """Requeue a failed or cancelled notification delivery."""

        async def op(principal):
            did = parse_uuid(delivery_id, field="delivery_id")
            async with get_session_factory()() as session:
                view = await notifications.retry_delivery(session, principal.user, did)
                result = {"delivery_id": str(did), "status": view.status}
                await session.commit()
                return result

        return await run_tool("events:write", op)
