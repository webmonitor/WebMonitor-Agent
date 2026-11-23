"""Personal access token management for MCP clients."""
from uuid import UUID

from fastapi import APIRouter, Query

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.schemas.api import ApiTokenCreate, ApiTokenCreated, ApiTokenView, Page
from webmonitor.services import tokens

router = APIRouter(prefix="/api/v1", tags=["tokens"])


@router.get("/tokens", response_model=Page[ApiTokenView])
async def list_tokens(
    session: DatabaseSession,
    user: AuthenticatedUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await tokens.list_tokens(session, user, limit=limit, offset=offset)


@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
async def create_token(
    body: ApiTokenCreate,
    session: DatabaseSession,
    user: AuthenticatedUser,
):
    row, raw = await tokens.create_token(
        session, user, name=body.name, scopes=body.scopes, ttl_days=body.ttl_days
    )
    view = tokens.token_view(row)
    await session.commit()
    return ApiTokenCreated(**view.model_dump(), token=raw)


@router.delete("/tokens/{token_id}", response_model=ApiTokenView)
async def revoke_token(
    token_id: UUID,
    session: DatabaseSession,
    user: AuthenticatedUser,
):
    row = await tokens.revoke_token(session, user, token_id)
    view = tokens.token_view(row)
    await session.commit()
    return view
