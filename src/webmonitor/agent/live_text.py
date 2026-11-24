"""Process-local display deltas; durable job text remains the recovery source."""
from uuid import UUID

_pending: dict[UUID, str] = {}


def append(job_id: UUID, delta: str) -> None:
    if delta:
        _pending[job_id] = _pending.get(job_id, "") + delta


def pending(job_id: UUID) -> str:
    return _pending.get(job_id, "")


def clear(job_id: UUID) -> None:
    _pending.pop(job_id, None)
