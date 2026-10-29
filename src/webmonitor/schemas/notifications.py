"""Strict notification payload contract; templates are packaged files."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

EventType = Literal['price_changed', 'list_changed', 'content_changed', 'run_failed', 'recovered']
EVENT_TYPES = frozenset(('price_changed', 'list_changed', 'content_changed', 'run_failed', 'recovered'))


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PayloadMonitor(Contract):
    id: UUID
    name: str
    url: str


class PayloadEvent(Contract):
    id: UUID
    type: EventType
    detected_at: datetime


class PayloadChange(Contract):
    before: dict[str, Any] | None
    after: dict[str, Any]
    summary: str


class NotificationPayload(Contract):
    monitor: PayloadMonitor
    event: PayloadEvent
    change: PayloadChange
    fields: dict[str, Any]
    evidence_url: str
