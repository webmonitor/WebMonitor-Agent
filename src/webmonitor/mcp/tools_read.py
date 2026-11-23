"""Read-only query and evidence inspection tools (requires `read` scope)."""
import base64
import json
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from sqlalchemy import select

from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.mcp.errors import parse_uuid, run_tool
from webmonitor.models import Job, Monitor, Snapshot
from webmonitor.schemas.notifications import EventType
from webmonitor.security.auth import require_owner
from webmonitor.services import conversations, events, monitors, notifications, templates
from webmonitor.storage.evidence import stream_evidence

READ_ONLY_LOCAL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
MAX_TEXT_EVIDENCE_BYTES = 65536
MAX_IMAGE_EVIDENCE_BYTES = 2 * 1024 * 1024


def _clamp_page(limit: int, offset: int) -> tuple[int, int]:
    return min(max(int(limit), 1), 100), max(int(offset), 0)


def register_read_tools(mcp: MCPServer) -> None:
    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_monitors(
        archived: bool = False, limit: int = 50, offset: int = 0
    ) -> CallToolResult:
        """List monitors owned by the authenticated user (or all monitors for admins)."""

        async def op(principal):
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await monitors.list_monitors(
                    session, principal.user, safe_limit, safe_offset, archived=archived
                )
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_monitor(monitor_id: str) -> CallToolResult:
        """Read full monitor detail including spec, baseline snapshot and redacted delivery metadata."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                detail = await monitors.read_monitor(session, principal.user, mid)
                return detail.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_snapshots(
        monitor_id: str, limit: int = 20, offset: int = 0
    ) -> CallToolResult:
        """List recent collection snapshots for a monitor."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await monitors.list_snapshots(
                    session, principal.user, mid, safe_limit, safe_offset
                )
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_snapshot(snapshot_id: str) -> CallToolResult:
        """Read a snapshot with its extracted data, coverage, evidence refs and published spec."""

        async def op(principal):
            sid = parse_uuid(snapshot_id, field="snapshot_id")
            async with get_session_factory()() as session:
                detail = await monitors.read_snapshot(session, principal.user, sid)
                return {**detail.model_dump(mode="json"), "untrusted_page_data": True}

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_events(
        monitor_id: str | None = None,
        event_type: EventType | None = None,
        acknowledged: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CallToolResult:
        """List change and failure events across owned monitors."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id") if monitor_id is not None else None
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await events.list_events(
                    session,
                    principal.user,
                    limit=safe_limit,
                    offset=safe_offset,
                    monitor_id=mid,
                    event_type=event_type,
                    acknowledged=acknowledged,
                )
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_monitor_jobs(
        monitor_id: str, limit: int = 20, offset: int = 0
    ) -> CallToolResult:
        """List production jobs for a monitor."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await monitors.list_monitor_jobs(
                    session, principal.user, mid, safe_limit, safe_offset
                )
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_job(job_id: str) -> CallToolResult:
        """Read job status, steps, attempts, result and associated snapshot."""

        async def op(principal):
            jid = parse_uuid(job_id, field="job_id")
            async with get_session_factory()() as session:
                job = await session.get(Job, jid)
                if job is None or (
                    job.user_id != principal.user.user_id and principal.user.role != "admin"
                ):
                    raise DomainError("not_found", 404)
                snapshot = await session.scalar(select(Snapshot).where(Snapshot.job_id == job.id))
                if job.kind == "production":
                    if job.monitor_id is None or job.revision is None:
                        raise DomainError("not_found", 404)
                    spec = await monitors.published_spec(session, job.monitor_id, job.revision)
                else:
                    spec = job.spec or {}
                return {
                    **conversations.job_view(job).model_dump(mode="json"),
                    "result": job.result,
                    "snapshot": (
                        monitors.snapshot_record(snapshot).model_dump(mode="json")
                        if snapshot is not None
                        else None
                    ),
                    "spec": spec,
                }

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_deliveries(
        monitor_id: str | None = None,
        status: Literal["queued", "sending", "retrying", "sent", "failed", "cancelled"] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CallToolResult:
        """List outbound email/webhook notification deliveries."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id") if monitor_id is not None else None
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await notifications.list_deliveries(
                    session,
                    principal.user,
                    limit=safe_limit,
                    offset=safe_offset,
                    status=status,
                    monitor_id=mid,
                )
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_notification_groups(limit: int = 50, offset: int = 0) -> CallToolResult:
        """List active notification groups (member email addresses are redacted for non-admins)."""

        async def op(principal):
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await notifications.list_groups(
                    session,
                    safe_limit,
                    safe_offset,
                    include_members=principal.user.role == "admin",
                )
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def list_email_templates(limit: int = 50, offset: int = 0) -> CallToolResult:
        """List reusable email templates."""

        async def op(principal):
            del principal
            safe_limit, safe_offset = _clamp_page(limit, offset)
            async with get_session_factory()() as session:
                page = await templates.list_templates(session, safe_limit, safe_offset)
                return page.model_dump(mode="json")

        return await run_tool("read", op)

    @mcp.tool(annotations=READ_ONLY_LOCAL)
    async def get_evidence(
        snapshot_id: str, index: int, max_bytes: int = 16384
    ) -> CallToolResult:
        """Read a bounded snapshot evidence artifact (screenshot image or truncated untrusted HTML/JSON)."""

        async def op(principal):
            sid = parse_uuid(snapshot_id, field="snapshot_id")
            async with get_session_factory()() as session:
                snapshot = await session.get(Snapshot, sid)
                if snapshot is None:
                    raise DomainError("not_found", 404)
                require_owner(principal.user, await session.get(Monitor, snapshot.monitor_id))
                refs = list(snapshot.evidence_refs or [])
            if index < 0 or index >= len(refs):
                raise DomainError("not_found", 404)
            reference = refs[index]
            if (
                not isinstance(reference, dict)
                or "bucket" not in reference
                or "object_key" not in reference
            ):
                raise DomainError("not_found", 404)

            kind = reference.get("kind") or ""
            cap = (
                MAX_IMAGE_EVIDENCE_BYTES
                if kind == "screenshot"
                else min(max(int(max_bytes), 256), MAX_TEXT_EVIDENCE_BYTES)
            )
            stream = await stream_evidence(reference["bucket"], reference["object_key"])
            buf = bytearray()
            truncated = False
            async for chunk in stream:
                remaining = cap - len(buf)
                if remaining <= 0:
                    truncated = True
                    break
                if len(chunk) > remaining:
                    buf.extend(chunk[:remaining])
                    truncated = True
                    break
                buf.extend(chunk)

            if kind == "screenshot" and not truncated:
                meta = {
                    "snapshot_id": str(sid),
                    "index": index,
                    "kind": kind,
                    "content_type": reference.get("content_type", "image/png"),
                    "sha256": reference.get("sha256"),
                    "size_bytes": len(buf),
                }
                return CallToolResult(
                    content=[
                        TextContent(type="text", text=json.dumps(meta, ensure_ascii=False)),
                        ImageContent(
                            type="image",
                            data=base64.b64encode(bytes(buf)).decode("ascii"),
                            mimeType="image/png",
                        ),
                    ],
                    is_error=False,
                )

            if kind == "screenshot" and truncated:
                return {
                    "snapshot_id": str(sid),
                    "index": index,
                    "kind": kind,
                    "content_type": reference.get("content_type"),
                    "sha256": reference.get("sha256"),
                    "size_bytes": reference.get("size_bytes"),
                    "truncated": True,
                    "message": "Screenshot exceeds 2 MiB inline limit",
                }

            return {
                "snapshot_id": str(sid),
                "index": index,
                "kind": kind,
                "content_type": reference.get("content_type"),
                "sha256": reference.get("sha256"),
                "size_bytes": reference.get("size_bytes"),
                "untrusted": True,
                "truncated": truncated,
                "text": bytes(buf).decode("utf-8", errors="replace"),
            }

        return await run_tool("read", op)
