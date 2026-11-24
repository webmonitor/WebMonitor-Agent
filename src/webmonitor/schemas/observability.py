"""Administrator-only operational metrics, derived from durable jobs and deliveries."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class QueueMetric(BaseModel):
    kind: str
    queued: int
    running: int


class CollectionMetric(BaseModel):
    mode: str
    succeeded: int
    failed: int
    success_rate: float | None
    average_duration_ms: float | None


class DeliveryMetric(BaseModel):
    active: int
    sent: int
    failed: int
    cancelled: int
    failure_rate: float


class UsageMetric(BaseModel):
    user_id: UUID
    email: str
    bucket: datetime
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


class SystemMetrics(BaseModel):
    generated_at: datetime
    hours: int
    queue: list[QueueMetric]
    collection: list[CollectionMetric]
    deliveries: DeliveryMetric
    usage: list[UsageMetric]
