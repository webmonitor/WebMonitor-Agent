"""Trusted execution context for agent tools."""
from dataclasses import dataclass
from uuid import UUID

from webmonitor.security.auth import CurrentUser


@dataclass(frozen=True)
class RuntimeContext:
    user: CurrentUser
    conversation_id: UUID
    job_id: UUID
    worker_id: str
