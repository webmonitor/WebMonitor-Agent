"""Evidence streams resolved by index into a stored reference list."""
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import Monitor, Snapshot
from webmonitor.security.auth import require_owner
from webmonitor.services import drafts
from webmonitor.storage.evidence import CONTENT_TYPES, stream_evidence

router = APIRouter(prefix="/api/v1", tags=["evidence"])

# The archive is an HTML document; it downloads as an attachment so untrusted
# markup never renders on this origin, but its filename keeps the extension.
_EVIDENCE_SUFFIXES = {"html": "html", "json": "json", "screenshot": "png"}
FALLBACK_MEDIA_TYPE = "application/octet-stream"


def evidence_media_type(reference: dict) -> str:
    content_type = reference.get("content_type")
    if content_type in CONTENT_TYPES.values():
        return content_type
    return FALLBACK_MEDIA_TYPE


def evidence_disposition(reference: dict) -> str:
    kind = reference.get("kind") or ""
    suffix = _EVIDENCE_SUFFIXES.get(kind)
    if suffix is None:
        suffix = "json" if evidence_media_type(reference).startswith("application/json") else "txt"
    disposition = "inline" if kind == "screenshot" else "attachment"
    name = reference.get("sha256", "evidence")[:16]
    return f'{disposition}; filename="{name}.{suffix}"'


async def _response(reference: dict) -> StreamingResponse:
    return StreamingResponse(
        await stream_evidence(reference["bucket"], reference["object_key"]),
        media_type=evidence_media_type(reference),
        headers={
            "Content-Disposition": evidence_disposition(reference),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        })


def _pick(references: list[dict], index: int) -> dict:
    if index < 0 or index >= len(references):
        raise DomainError("not_found", 404)
    reference = references[index]
    if not isinstance(reference, dict) or "bucket" not in reference or "object_key" not in reference:
        raise DomainError("not_found", 404)
    return reference


@router.get("/snapshots/{snapshot_id}/evidence/{index}")
async def snapshot_evidence(snapshot_id: UUID, index: int, session: DatabaseSession,
                            user: AuthenticatedUser):
    snapshot = await session.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise DomainError("not_found", 404)
    require_owner(user, await session.get(Monitor, snapshot.monitor_id))
    return await _response(_pick(list(snapshot.evidence_refs or []), index))


@router.get("/drafts/{draft_id}/evidence/{index}")
async def draft_evidence(draft_id: UUID, index: int, session: DatabaseSession,
                         user: AuthenticatedUser):
    draft = await drafts.require_draft(session, user, draft_id)
    references = list((draft.extraction_preview or {}).get("evidence_refs") or [])
    return await _response(_pick(references, index))
