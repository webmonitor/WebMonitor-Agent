"""Trusted execution context for agent tools."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.models import Draft
from webmonitor.schemas.monitors import DraftSpec
from webmonitor.security.auth import CurrentUser


@dataclass
class RuntimeContext:
    user: CurrentUser
    conversation_id: UUID
    job_id: UUID
    worker_id: str
    draft_id: UUID | None = None
    draft_revision: int | None = None
    draft_spec: DraftSpec | None = None
    monitor_id: UUID | None = None

    def update_draft(self, draft: Draft) -> None:
        self.draft_id = draft.id
        self.draft_revision = draft.revision
        self.draft_spec = DraftSpec.model_validate(draft.spec) if draft.spec is not None else None
        self.monitor_id = draft.monitor_id


async def current_draft(session: AsyncSession, conversation_id: UUID, *,
                        lock: bool = False) -> Draft | None:
    query = select(Draft).where(Draft.conversation_id == conversation_id).order_by(
        Draft.created_at.desc(), Draft.id.desc()).limit(1)
    if lock:
        query = query.with_for_update()
    return await session.scalar(query.execution_options(populate_existing=True))
