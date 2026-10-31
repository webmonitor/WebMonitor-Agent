"""Request and response contracts shared by HTTP routes."""
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator

T = TypeVar("T")

Role = Literal["admin", "member"]
JobKind = Literal["agent", "analyze", "preview", "production"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled", "discarded"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int


# ---- requests ---------------------------------------------------------------

class PostMessageRequest(Input):
    content: str = Field(min_length=1)
    client_message_id: str = Field(min_length=1, max_length=64)


class ConversationCreate(Input):
    title: str | None = Field(default=None, max_length=200)
    # Sending the first message in the same request keeps an abandoned draft from
    # leaving an unnamed conversation behind.
    message: PostMessageRequest | None = None


class ApproveRequest(Input):
    draft_id: UUID
    revision: int = Field(ge=1, strict=True)
    preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class MemberSpec(Input):
    email: EmailStr
    active: StrictBool = True

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return value.strip().casefold() if isinstance(value, str) else value


class GroupSpec(Input):
    name: str = Field(min_length=1, max_length=200)
    enabled: StrictBool = True
    members: list[MemberSpec] = Field(default_factory=list)

    @field_validator("members")
    @classmethod
    def unique_members(cls, value: list[MemberSpec]) -> list[MemberSpec]:
        if len({str(member.email) for member in value}) != len(value):
            raise ValueError("duplicate recipient email")
        return value


class GroupPatch(Input):
    name: str | None = Field(default=None, max_length=200)
    enabled: StrictBool | None = None
    members: list[MemberSpec] | None = None


class Availability(Input):
    active: StrictBool


# ---- responses --------------------------------------------------------------

class MessageView(BaseModel):
    id: UUID
    role: str
    content: str
    job_id: UUID | None
    client_message_id: str | None
    created_at: datetime


class JobStep(BaseModel):
    name: str
    status: str
    at: str
    error_code: str | None = None
    detail: str | None = None


class JobAttempt(BaseModel):
    number: int
    status: str
    started_at: str
    finished_at: str | None = None
    error_code: str | None = None
    retryable: bool = False


class JobView(BaseModel):
    id: UUID
    kind: str
    status: str
    conversation_id: UUID | None
    draft_id: UUID | None
    monitor_id: UUID | None
    revision: int | None
    url: str | None
    partial_text: str
    steps: list[JobStep]
    attempts: list[JobAttempt]
    attempt_count: int
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime


class EvidenceRef(BaseModel):
    kind: str
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int
    sha256: str


class DraftView(BaseModel):
    id: UUID
    conversation_id: UUID
    revision: int
    status: str
    spec: dict[str, Any] | None
    spec_hash: str | None
    preview: dict[str, Any] | None
    preview_hash: str | None
    preview_expires_at: datetime | None
    monitor_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ConversationView(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class Limits(BaseModel):
    message_max_chars: int
    preview_ttl_minutes: int


class ConversationSnapshot(BaseModel):
    conversation: ConversationView
    messages: list[MessageView]
    jobs: list[JobView]
    drafts: list[DraftView]
    limits: Limits


class MonitorView(BaseModel):
    id: UUID
    name: str
    url: str
    status: str
    collection_mode: str
    spec_version: int
    interval_seconds: int
    timezone: str
    baseline_status: str
    health_status: str
    notification_group_ids: list[str]
    next_run_at: datetime
    last_success_at: datetime | None
    last_failure_at: datetime | None
    created_at: datetime


class SnapshotRecord(BaseModel):
    id: UUID
    job_id: UUID
    spec_version: int
    final_url: str
    extracted_data: dict[str, Any]
    coverage: dict[str, Any]
    evidence_refs: list[EvidenceRef]
    collected_at: datetime


class MonitorDetail(MonitorView):
    spec: dict[str, Any]
    baseline: SnapshotRecord | None


class JobDetail(JobView):
    result: dict[str, Any] | None
    snapshot: SnapshotRecord | None


class EventView(BaseModel):
    id: UUID
    monitor_id: UUID
    monitor_name: str
    job_id: UUID
    snapshot_id: UUID | None
    type: str
    change: dict[str, Any]
    created_at: datetime
    acknowledged_at: datetime | None


class Group(BaseModel):
    id: UUID
    name: str
    enabled: bool
    members: list[MemberSpec]
    created_at: datetime
    updated_at: datetime


class Delivery(BaseModel):
    id: UUID
    monitor_id: UUID
    event_id: UUID
    recipient: str
    subject: str
    body_text: str
    status: str
    attempt_count: int
    error_code: str | None
    error_message: str | None
    smtp_response_code: int | None
    created_at: datetime
    sent_at: datetime | None
    failed_at: datetime | None


class Member(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    active: bool
    created_at: datetime


class CreateMonitorResult(BaseModel):
    monitor_id: UUID
    status: str
    baseline_status: str
    next_run_at: datetime


class DerivedDraft(BaseModel):
    conversation_id: UUID
    draft_id: UUID
    revision: int
