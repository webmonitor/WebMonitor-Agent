"""The complete relational model, with explicit recipient approvals per monitor.

`jobs` replaces runs, attempts, collection jobs, agent runs and the outbox. A job row
carries its own lease, attempt history and result, so every asynchronous operation
(scheduling, collection, preview, analysis, agent turn) shares one claim protocol.
"""
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _timestamp():
    return mapped_column(DateTime(timezone=True), default=utc_now, server_default=func.now())


class UUIDPrimaryKey:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)


class Created:
    created_at: Mapped[datetime] = _timestamp()


class Updated:
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now,
                                                 server_default=func.now(), onupdate=utc_now)


class User(UUIDPrimaryKey, Created, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'member')", name="role"),
        CheckConstraint("email = lower(btrim(email)) AND email <> ''", name="normalized_email"),
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="member", server_default="member")
    active: Mapped[bool] = mapped_column(default=True, server_default="true")


class Session(UUIDPrimaryKey, Created, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_live_user", "user_id", "expires_at",
              postgresql_where=text("revoked_at IS NULL")),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invitation(UUIDPrimaryKey, Created, Base):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("email = lower(btrim(email)) AND email <> ''", name="normalized_email"),
        Index("ix_invitations_pending_email", "email",
              postgresql_where=text("consumed_at IS NULL")),
    )
    email: Mapped[str] = mapped_column(String(320))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(UUIDPrimaryKey, Created, Updated, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(200))


class Message(UUIDPrimaryKey, Created, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id"),
        CheckConstraint("role IN ('user', 'assistant', 'system')", name="role"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at", "id"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"))
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    client_message_id: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)


class Job(UUIDPrimaryKey, Created, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("kind IN ('agent', 'analyze', 'preview', 'production')", name="kind"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled', 'discarded')", name="status"),
        Index("uq_jobs_active_production", "monitor_id", unique=True,
              postgresql_where=text("kind = 'production' AND status IN ('queued', 'running')")),
        Index("uq_jobs_active_preview", "draft_id", "revision", unique=True,
              postgresql_where=text("kind = 'preview' AND status IN ('queued', 'running')")),
        Index("uq_jobs_active_agent", "conversation_id", unique=True,
              postgresql_where=text("kind = 'agent' AND status IN ('queued', 'running')")),
        Index("ix_jobs_claimable", "kind", "status", "available_at"),
        Index("ix_jobs_conversation", "conversation_id", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    conversation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"))
    draft_id: Mapped[UUID | None] = mapped_column(ForeignKey("drafts.id", ondelete="SET NULL"))
    revision: Mapped[int | None] = mapped_column(Integer)
    monitor_id: Mapped[UUID | None] = mapped_column(index=True)
    url: Mapped[str | None] = mapped_column(Text)
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    partial_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = _timestamp()
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class Draft(UUIDPrimaryKey, Created, Updated, Base):
    __tablename__ = "drafts"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'discarded')", name="status"),
        CheckConstraint("revision >= 0", name="revision"),
        Index("ix_drafts_conversation", "conversation_id", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"))
    monitor_id: Mapped[UUID | None] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    spec_hash: Mapped[str | None] = mapped_column(String(64))
    preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    preview_hash: Mapped[str | None] = mapped_column(String(64))
    preview_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")


class Monitor(UUIDPrimaryKey, Created, Updated, Base):
    __tablename__ = "monitors"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused')", name="status"),
        CheckConstraint("baseline_status IN ('pending_first_success', 'ready')", name="baseline_status"),
        CheckConstraint("health_status IN ('healthy', 'failed')", name="health_status"),
        CheckConstraint("collection_mode IN ('http', 'browser')", name="collection_mode"),
        Index("ix_monitors_due", "next_run_at", postgresql_where=text("status = 'active'")),
        Index("ix_monitors_user_created", "user_id", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    draft_id: Mapped[UUID] = mapped_column(ForeignKey("drafts.id"), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    spec_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    spec_hash: Mapped[str] = mapped_column(String(64))
    collection_mode: Mapped[str] = mapped_column(String(16))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(100))
    notification_group_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    approved_recipients: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    baseline_snapshot_id: Mapped[UUID | None] = mapped_column(index=True)
    baseline_status: Mapped[str] = mapped_column(String(32), default="pending_first_success",
                                                 server_default="pending_first_success")
    rule_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    next_run_at: Mapped[datetime] = _timestamp()
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str] = mapped_column(String(16), default="healthy", server_default="healthy")
    failure_fingerprint: Mapped[str | None] = mapped_column(String(64))
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Snapshot(UUIDPrimaryKey, Created, Base):
    __tablename__ = "snapshots"
    __table_args__ = (
        CheckConstraint("spec_version > 0", name="spec_version"),
        Index("ix_snapshots_monitor_collected", "monitor_id", "collected_at"),
    )
    monitor_id: Mapped[UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"), unique=True)
    spec_version: Mapped[int] = mapped_column(Integer)
    final_url: Mapped[str] = mapped_column(Text)
    extracted_data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rule_state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Event(UUIDPrimaryKey, Created, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("job_id", "type"),
        CheckConstraint("type IN ('price_changed', 'list_changed', 'content_changed', 'run_failed', 'recovered')", name="type"),
        Index("ix_events_monitor_created", "monitor_id", "created_at"),
    )
    monitor_id: Mapped[UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id"))
    snapshot_id: Mapped[UUID | None] = mapped_column(ForeignKey("snapshots.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(32))
    change: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    failure_fingerprint: Mapped[str | None] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"))


class NotificationGroup(UUIDPrimaryKey, Created, Updated, Base):
    __tablename__ = "notification_groups"
    __table_args__ = (
        Index("uq_notification_groups_name", "name", unique=True,
              postgresql_where=text("deleted_at IS NULL")),
    )
    name: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(default=True, server_default="true")
    members: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailDelivery(UUIDPrimaryKey, Created, Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sending', 'retrying', 'sent', 'failed', 'cancelled')", name="status"),
        Index("ix_email_deliveries_created", "created_at"),
        Index("ix_email_deliveries_event", "event_id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    monitor_id: Mapped[UUID] = mapped_column(ForeignKey("monitors.id", ondelete="CASCADE"))
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    html: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    available_at: Mapped[datetime] = _timestamp()
    lease_owner: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    smtp_response_code: Mapped[int | None] = mapped_column(Integer)
    message_id: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
