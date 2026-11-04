"""Reusable email templates: user-authored designs, shared across the workspace.

A template is data, never code: it is validated against the structured schema, and
every monitor keeps the config snapshot it was approved with, so editing or deleting
a template never rewrites an existing monitor or a queued delivery.
"""
import asyncio
import logging
import time
from collections import defaultdict, deque
from uuid import UUID

from openai import APIConnectionError, APIStatusError, AsyncOpenAI
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.agent.template_draft import Proposal, draft_template
from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import EmailTemplate, utc_now
from webmonitor.notifications.custom import preview_template as render_preview
from webmonitor.schemas.api import EmailTemplatePatch, EmailTemplateSpec, EmailTemplateView, Page
from webmonitor.schemas.templates import EmailTemplateConfig
from webmonitor.security.auth import CurrentUser, is_admin


def template_view(template: EmailTemplate) -> EmailTemplateView:
    return EmailTemplateView(id=template.id, name=template.name,
        description=template.description or "", config=template.config or {},
        created_by_user_id=template.created_by_user_id,
        created_at=template.created_at, updated_at=template.updated_at)


def config_of(template: EmailTemplate) -> EmailTemplateConfig:
    """A stored config that no longer validates cannot be used for new mail."""
    try:
        return EmailTemplateConfig.model_validate(template.config or {})
    except ValueError:
        raise DomainError("template_unavailable", 409) from None


async def list_templates(session: AsyncSession, limit: int, offset: int) -> Page[EmailTemplateView]:
    query = select(EmailTemplate).where(EmailTemplate.deleted_at.is_(None))
    rows = (await session.scalars(query.order_by(EmailTemplate.name)
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[EmailTemplateView](items=[template_view(row) for row in rows], total=total or 0)


async def get_template(session: AsyncSession, template_id: UUID,
                       *, lock: bool = False) -> EmailTemplate:
    query = select(EmailTemplate).where(EmailTemplate.id == template_id,
                                        EmailTemplate.deleted_at.is_(None))
    if lock:
        query = query.with_for_update()
    template = await session.scalar(query.execution_options(populate_existing=True))
    if template is None:
        raise DomainError("template_not_found", 404)
    return template


def _editable(user: CurrentUser, template: EmailTemplate) -> None:
    """Any member may author a template; only its creator an admin may change it."""
    if not is_admin(user) and template.created_by_user_id != user.user_id:
        raise DomainError("forbidden", 403)


async def write_template(session: AsyncSession, user: CurrentUser,
                         body: EmailTemplateSpec | EmailTemplatePatch, *,
                         template_id: UUID | None = None) -> EmailTemplate:
    try:
        async with session.begin_nested():
            if template_id is None:
                if not isinstance(body, EmailTemplateSpec):
                    raise DomainError("validation_failed", 422)
                template = EmailTemplate(name=body.name, description=body.description,
                    config=body.config.model_dump(mode="json"),
                    created_by_user_id=user.user_id)
                session.add(template)
                await session.flush()
            else:
                template = await get_template(session, template_id, lock=True)
                _editable(user, template)
                if body.name is not None:
                    template.name = body.name
                if body.description is not None:
                    template.description = body.description
                if body.config is not None:
                    template.config = body.config.model_dump(mode="json")
                await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError("template_name_conflict", 409) from None
        raise
    return template


async def disable_template(session: AsyncSession, user: CurrentUser,
                           template_id: UUID) -> EmailTemplate:
    template = await get_template(session, template_id, lock=True)
    _editable(user, template)
    template.deleted_at = utc_now()
    await session.flush()
    return template


def preview(config: EmailTemplateConfig) -> list[dict]:
    return render_preview(config)


logger = logging.getLogger(__name__)

# Generation is a paid model call; one process bounds it per user per hour.
_template_runs: dict[UUID, deque[float]] = defaultdict(deque)
_template_lock = asyncio.Lock()


async def _reserve_generation(user_id: UUID) -> None:
    limit = get_settings().template_generation_per_hour
    now = time.monotonic()
    async with _template_lock:
        recent = _template_runs[user_id]
        while recent and now - recent[0] > 3600:
            recent.popleft()
        if len(recent) >= limit:
            retry_after = max(1, int(3600 - (now - recent[0])) + 1)
            raise DomainError("rate_limited", 429,
                              details={"retry_after": retry_after, "limit": limit})
        recent.append(now)


async def draft(description: str, *, user: CurrentUser) -> Proposal:
    """Ask the model for one design. Nothing is written; the caller reviews it."""
    settings = get_settings()
    if not settings.openai_api_key.get_secret_value() or not settings.openai_model:
        raise DomainError("model_unavailable", 503)
    await _reserve_generation(user.user_id)
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.model_base_url,
        timeout=settings.agent_model_timeout_seconds, max_retries=0)
    try:
        async with asyncio.timeout(settings.agent_model_timeout_seconds * 2):
            return await draft_template(description, client=client,
                                        model=settings.openai_model)
    except TimeoutError:
        raise DomainError("template_generation_failed", 503,
                          "Template generation timed out") from None
    except (APIConnectionError, APIStatusError) as exc:
        logger.info("Template generation model call failed: %s", type(exc).__name__)
        raise DomainError("model_unavailable", 503) from None
    finally:
        await client.close()
