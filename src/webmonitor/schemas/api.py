"""Request and response contracts shared by HTTP routes."""
from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.schemas.templates import EmailTemplateConfig

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
    # The service enforces the configured limit; this is only the abuse ceiling.
    content: str = Field(min_length=1, max_length=200_000)
    client_message_id: str = Field(min_length=1, max_length=64)


class ConversationCreate(Input):
    title: str | None = Field(default=None, max_length=200)
    # Sending the first message in the same request keeps an abandoned draft from
    # leaving an unnamed conversation behind.
    message: PostMessageRequest | None = None


class ApproveRequest(Input):
    draft_id: UUID
    spec_revision: int = Field(ge=0, strict=True)
    settings_revision: int = Field(ge=0, strict=True)
    extraction_preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    delivery_preview_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class DraftUpdate(Input):
    """Each section carries its own revision, so an edit cannot overwrite the other."""

    spec_revision: int | None = Field(default=None, ge=0, strict=True)
    settings_revision: int | None = Field(default=None, ge=0, strict=True)
    spec: MonitorSpec | None = None
    settings: DeliverySettings | None = None

    @model_validator(mode="after")
    def sections(self) -> "DraftUpdate":
        if self.spec is None and self.settings is None:
            raise ValueError("spec or settings is required")
        if self.spec is not None and self.spec_revision is None:
            raise ValueError("spec requires spec_revision")
        if self.settings is not None and self.settings_revision is None:
            raise ValueError("settings requires settings_revision")
        return self


class EmailTemplateSpec(Input):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    config: EmailTemplateConfig

    @field_validator("name")
    @classmethod
    def trimmed_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class EmailTemplatePrompt(Input):
    """One sentence is the whole input; the model returns the design."""

    description: str = Field(min_length=1, max_length=1000)

    @field_validator("description")
    @classmethod
    def trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description must not be blank")
        return value


class EmailTemplatePatch(Input):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    config: EmailTemplateConfig | None = None

    @field_validator("name")
    @classmethod
    def trimmed_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class MonitorSettingsUpdate(Input):
    """Who is told and how often, edited on the monitor itself."""

    settings: DeliverySettings


class MonitorRename(Input):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class InvitationCreate(Input):
    email: EmailStr
    ttl_hours: int = Field(default=24, ge=1, le=168, strict=True)


class MemberSpec(Input):
    email: EmailStr
    active: StrictBool = True

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value: Any) -> Any:
        return value.strip().casefold() if isinstance(value, str) else value


def unique_members(members: list[MemberSpec]) -> list[MemberSpec]:
    if len({str(member.email) for member in members}) != len(members):
        raise ValueError("duplicate recipient email")
    return members


class GroupSpec(Input):
    name: str = Field(min_length=1, max_length=200)
    enabled: StrictBool = True
    members: list[MemberSpec] = Field(default_factory=list, max_length=500)

    @field_validator("name")
    @classmethod
    def trimmed_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("members")
    @classmethod
    def checked_members(cls, value: list[MemberSpec]) -> list[MemberSpec]:
        return unique_members(value)


class GroupPatch(Input):
    name: str | None = Field(default=None, max_length=200)
    enabled: StrictBool | None = None
    members: list[MemberSpec] | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def trimmed_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("members")
    @classmethod
    def checked_members(cls, value: list[MemberSpec] | None) -> list[MemberSpec] | None:
        return None if value is None else unique_members(value)


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
    # A started step has no duration yet; a finished one reports its own elapsed time.
    duration_ms: int | None = None


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
    status: str
    spec: dict[str, Any] | None
    spec_hash: str | None
    spec_revision: int
    settings: dict[str, Any]
    settings_hash: str | None
    settings_revision: int
    extraction_preview: dict[str, Any] | None
    extraction_preview_hash: str | None
    extraction_preview_expires_at: datetime | None
    delivery_preview: dict[str, Any] | None
    delivery_preview_hash: str | None
    delivery_preview_expires_at: datetime | None
    monitor_id: UUID | None
    created_at: datetime
    updated_at: datetime


class RenderedEmail(BaseModel):
    event_type: str
    subject: str
    html: str
    text: str
    preview_html: str


class ExtractionPreview(BaseModel):
    """What a real collection produced for the saved collection contract."""

    preview_id: str
    spec_revision: int
    spec_hash: str
    extracted_data: dict[str, Any]
    coverage: dict[str, Any]
    final_url: str | None
    evidence_refs: list[EvidenceRef]
    rule_simulation: dict[str, Any]
    source: Any | None = None
    warnings: list[str]
    created_at: datetime
    expires_at: datetime


class DeliveryPreview(BaseModel):
    """What the mail will look like for the current settings and template."""

    preview_id: str
    settings_revision: int
    settings_hash: str
    template_id: UUID | None
    template_name: str | None
    template_hash: str
    rendered_emails: list[RenderedEmail]
    recipients: list[str]
    recipient_sources: list[dict[str, Any]]
    warnings: list[str]
    created_at: datetime
    expires_at: datetime


class EmailTemplateView(BaseModel):
    id: UUID
    name: str
    description: str
    config: dict[str, Any]
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class EmailTemplatePreview(BaseModel):
    rendered_emails: list[RenderedEmail]


class EmailTemplateProposal(BaseModel):
    """A generated design; the user still has to save it."""

    name: str
    config: EmailTemplateConfig


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
    email_template_id: UUID | None = None
    next_run_at: datetime
    last_success_at: datetime | None
    last_failure_at: datetime | None
    created_at: datetime
    archived_at: datetime | None = None


class SnapshotRecord(BaseModel):
    id: UUID
    job_id: UUID
    spec_version: int
    final_url: str
    extracted_data: dict[str, Any]
    coverage: dict[str, Any]
    evidence_refs: list[EvidenceRef]
    collected_at: datetime


class SnapshotDetail(SnapshotRecord):
    monitor_id: UUID
    monitor_name: str


class MonitorDetail(MonitorView):
    spec: dict[str, Any]
    baseline: SnapshotRecord | None
    approved_recipients: list[str] = Field(default_factory=list)
    email_template: dict[str, Any] | None = None


class SpecVersion(BaseModel):
    id: UUID
    version: int
    draft_id: UUID
    spec: dict[str, Any]
    spec_hash: str
    published_at: datetime
    current: bool


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
    # Why no mail was generated for this event; NULL means it was routed normally.
    notifications_skipped: str | None = None


class Group(BaseModel):
    id: UUID
    name: str
    enabled: bool
    members: list[MemberSpec]
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class Delivery(BaseModel):
    id: UUID
    monitor_id: UUID
    monitor_name: str
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


class InvitationView(BaseModel):
    id: UUID
    email: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None


class InvitationCreated(BaseModel):
    email: str
    url: str
    expires_at: datetime


class CreateMonitorResult(BaseModel):
    monitor_id: UUID
    status: str
    baseline_status: str
    next_run_at: datetime


class DerivedDraft(BaseModel):
    conversation_id: UUID
    draft_id: UUID
    spec_revision: int
    settings_revision: int
