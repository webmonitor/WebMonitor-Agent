"""Draft authoring, delivery settings, preview and guarded approval tools."""
from typing import Any

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, ToolAnnotations

from webmonitor.config import get_settings
from webmonitor.db import get_session_factory
from webmonitor.errors import DomainError
from webmonitor.mcp.errors import bound_untrusted_json, coerce_spec_input, parse_uuid, run_tool
from webmonitor.mcp.tools_discover import _clamp_timeout, _wait_with_progress
from webmonitor.models import Conversation
from webmonitor.schemas.api import ApproveRequest
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.services import conversations, drafts


def register_draft_tools(mcp: MCPServer) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def derive_draft_from_monitor(monitor_id: str) -> CallToolResult:
        """Create an editable conversation and draft seeded from an existing monitor."""

        async def op(principal):
            mid = parse_uuid(monitor_id, field="monitor_id")
            async with get_session_factory()() as session:
                conversation, draft = await drafts.draft_from_monitor(
                    session, principal.user, mid
                )
                await session.commit()
                return {
                    "conversation_id": str(conversation.id),
                    "draft_id": str(draft.id),
                    "monitor_id": str(draft.monitor_id) if draft.monitor_id else None,
                    "spec_revision": draft.spec_revision,
                    "settings_revision": draft.settings_revision,
                    "spec": draft.spec,
                    "settings": draft.settings,
                }

        return await run_tool("drafts:write", op)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def save_monitor_draft(
        spec: dict[str, Any] | str,
        draft_id: str | None = None,
        expected_revision: int | None = None,
        conversation_id: str | None = None,
    ) -> CallToolResult:
        """Save a validated MonitorSpec to a new or existing draft."""

        async def op(principal):
            parsed = coerce_spec_input(spec)
            async with get_session_factory()() as session:
                if draft_id is not None:
                    existing = await drafts.require_draft(
                        session, principal.user, parse_uuid(draft_id, field="draft_id")
                    )
                    target_conversation_id = existing.conversation_id
                    target_draft_id = existing.id
                else:
                    target_draft_id = None
                    if conversation_id is not None:
                        conversation = await conversations.require_conversation(
                            session,
                            principal.user,
                            parse_uuid(conversation_id, field="conversation_id"),
                        )
                        target_conversation_id = conversation.id
                    else:
                        conversation = Conversation(
                            user_id=principal.user.user_id,
                            title=f"MCP: {parsed.name}"[:200],
                        )
                        session.add(conversation)
                        await session.flush()
                        target_conversation_id = conversation.id

                saved = await drafts.save_spec(
                    session,
                    principal.user,
                    conversation_id=target_conversation_id,
                    spec=parsed,
                    draft_id=target_draft_id,
                    expected_revision=expected_revision,
                )
                await session.commit()
                return {
                    "conversation_id": str(saved.conversation_id),
                    "draft_id": str(saved.id),
                    "monitor_id": str(saved.monitor_id) if saved.monitor_id else None,
                    "spec_revision": saved.spec_revision,
                    "settings_revision": saved.settings_revision,
                    "spec_hash": saved.spec_hash,
                    "spec": saved.spec,
                }

        return await run_tool("drafts:write", op, is_spec=True)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    async def update_draft_settings(
        draft_id: str,
        settings_revision: int,
        settings: dict[str, Any],
    ) -> CallToolResult:
        """Update delivery channel, notification groups, schedule or email template on a draft."""

        async def op(principal):
            did = parse_uuid(draft_id, field="draft_id")
            parsed = DeliverySettings.model_validate(settings)
            async with get_session_factory()() as session:
                saved = await drafts.save_settings(
                    session,
                    principal.user,
                    draft_id=did,
                    revision=settings_revision,
                    settings=parsed,
                )
                view = conversations.draft_view(saved, principal.user).model_dump(mode="json")
                await session.commit()
                return view

        return await run_tool("drafts:write", op)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        )
    )
    async def preview_monitor_draft(
        draft_id: str,
        spec_revision: int,
        wait: bool = True,
        timeout_seconds: int = 70,
        ctx: Context | None = None,
    ) -> CallToolResult:
        """Run real worker collection, evidence storage, rule simulation and delivery rendering for a draft."""

        async def op(principal):
            did = parse_uuid(draft_id, field="draft_id")
            async with get_session_factory()() as session:
                draft = await drafts.require_draft(session, principal.user, did, lock=True)
                if draft.spec_revision != spec_revision:
                    raise DomainError("stale_revision", 409)
                preview_job = await drafts.start_preview(session, principal.user, draft.id)
                await session.commit()

            if not wait:
                return {
                    "status": "queued",
                    "job_id": str(preview_job.id),
                    "draft_id": str(did),
                    "spec_revision": spec_revision,
                }

            await _wait_with_progress(
                preview_job.id,
                timeout=_clamp_timeout(timeout_seconds),
                cancel_on_timeout=True,
                ctx=ctx,
            )

            async with get_session_factory()() as session:
                draft = await drafts.require_draft(session, principal.user, did)
                extraction = drafts.validate_extraction_preview(draft)
                view = conversations.draft_view(draft, principal.user)
                bounded = bound_untrusted_json(
                    extraction.get("extracted_data"),
                    max_bytes=8192,
                    label="untrusted_field_summary",
                )
                return {
                    "status": "succeeded",
                    "draft_id": str(draft.id),
                    "conversation_id": str(draft.conversation_id),
                    "spec_revision": draft.spec_revision,
                    "settings_revision": draft.settings_revision,
                    "extraction_preview_hash": draft.extraction_preview_hash,
                    "delivery_preview_hash": draft.delivery_preview_hash,
                    "extraction_preview_expires_at": extraction.get("expires_at"),
                    "delivery_preview_expires_at": (
                        draft.delivery_preview_expires_at.isoformat()
                        if draft.delivery_preview_expires_at
                        else None
                    ),
                    "extracted_data": bounded["data"],
                    "untrusted_field_summary": bounded["untrusted_field_summary"],
                    "fields_truncated": bounded["truncated"],
                    "untrusted_page_data": True,
                    "coverage": extraction.get("coverage"),
                    "final_url": extraction.get("final_url"),
                    "evidence_refs": [
                        {
                            "kind": item.get("kind"),
                            "sha256": item.get("sha256"),
                            "size_bytes": item.get("size_bytes"),
                        }
                        for item in extraction.get("evidence_refs") or []
                    ],
                    "rule_simulation": extraction.get("rule_simulation") or {},
                    "delivery_preview": view.delivery_preview,
                    "warnings": extraction.get("warnings") or [],
                    "approval_url": (
                        f"{get_settings().app_origin}/app?conversation={draft.conversation_id}"
                    ),
                }

        return await run_tool("drafts:write", op)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    async def approve_draft(
        draft_id: str,
        spec_revision: int,
        settings_revision: int,
        extraction_preview_hash: str,
        delivery_preview_hash: str,
    ) -> CallToolResult:
        """Publish a previewed draft into a live monitor (requires drafts:approve scope and valid preview hashes)."""

        async def op(principal):
            payload = ApproveRequest(
                draft_id=parse_uuid(draft_id, field="draft_id"),
                spec_revision=spec_revision,
                settings_revision=settings_revision,
                extraction_preview_hash=extraction_preview_hash,
                delivery_preview_hash=delivery_preview_hash,
            )
            async with get_session_factory()() as session:
                draft = await drafts.require_draft(session, principal.user, payload.draft_id)
                monitor = await drafts.publish_draft(
                    session,
                    principal.user,
                    conversation_id=draft.conversation_id,
                    draft_id=payload.draft_id,
                    spec_revision=payload.spec_revision,
                    settings_revision=payload.settings_revision,
                    extraction_preview_hash=payload.extraction_preview_hash,
                    delivery_preview_hash=payload.delivery_preview_hash,
                )
                result = drafts.monitor_result(monitor).model_dump(mode="json")
                await session.commit()
                return result

        return await run_tool("drafts:approve", op)
