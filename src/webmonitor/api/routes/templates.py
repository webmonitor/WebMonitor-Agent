"""Reusable email templates: list, author, update, disable and preview."""
from uuid import UUID

from fastapi import APIRouter, Query

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.schemas.api import (
    EmailTemplatePatch,
    EmailTemplatePreview,
    EmailTemplateProposal,
    EmailTemplatePrompt,
    EmailTemplateSpec,
    EmailTemplateView,
    Page,
)
from webmonitor.schemas.templates import EmailTemplateConfig
from webmonitor.services import templates

router = APIRouter(prefix="/api/v1", tags=["templates"])


@router.get("/email-templates", response_model=Page[EmailTemplateView])
async def list_templates(session: DatabaseSession, user: AuthenticatedUser,
                         limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await templates.list_templates(session, limit, offset)


@router.post("/email-templates", response_model=EmailTemplateView, status_code=201)
async def create_template(body: EmailTemplateSpec, session: DatabaseSession,
                          user: AuthenticatedUser):
    template = await templates.write_template(session, user, body)
    result = templates.template_view(template)
    await session.commit()
    return result


@router.patch("/email-templates/{template_id}", response_model=EmailTemplateView)
async def patch_template(template_id: UUID, body: EmailTemplatePatch, session: DatabaseSession,
                         user: AuthenticatedUser):
    template = await templates.write_template(session, user, body, template_id=template_id)
    result = templates.template_view(template)
    await session.commit()
    return result


@router.delete("/email-templates/{template_id}", response_model=EmailTemplateView)
async def delete_template(template_id: UUID, session: DatabaseSession, user: AuthenticatedUser):
    template = await templates.disable_template(session, user, template_id)
    result = templates.template_view(template)
    await session.commit()
    return result


@router.post("/email-templates/generate", response_model=EmailTemplateProposal)
async def generate_template(body: EmailTemplatePrompt, session: DatabaseSession,
                            user: AuthenticatedUser):
    """One sentence in, one design out. Nothing is saved until the user saves it."""
    del session, user
    proposal = await templates.draft(body.description)
    return EmailTemplateProposal(name=proposal.name, config=proposal.config)


@router.post("/email-templates/preview", response_model=EmailTemplatePreview)
async def preview_template(body: EmailTemplateConfig, session: DatabaseSession,
                           user: AuthenticatedUser):
    """Render a candidate design without persisting it; a name is not required."""
    del session, user
    return EmailTemplatePreview(rendered_emails=templates.preview(body))
