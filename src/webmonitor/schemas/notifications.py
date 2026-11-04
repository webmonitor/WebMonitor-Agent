"""Strict notification payload contract; templates are packaged files."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal['content_changed', 'list_changed', 'run_failed', 'recovered']
EVENT_TYPES = frozenset(('content_changed', 'list_changed', 'run_failed', 'recovered'))


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PayloadMonitor(Contract):
    id: UUID
    name: str
    url: str
    timezone: str = "UTC"


class PayloadEvent(Contract):
    id: UUID
    type: EventType
    detected_at: datetime


class PayloadChange(Contract):
    before: dict[str, Any] | None
    after: dict[str, Any]
    summary: str
    # The readable evidence travels with the event: field labels and the exact
    # rows that were added, removed or updated.
    differences: list[dict[str, Any]] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class NotificationPayload(Contract):
    monitor: PayloadMonitor
    event: PayloadEvent
    change: PayloadChange
    fields: dict[str, Any]
    evidence_url: str
