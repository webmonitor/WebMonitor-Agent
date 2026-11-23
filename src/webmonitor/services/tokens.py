"""Personal access tokens for external MCP clients."""
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.errors import DomainError
from webmonitor.models import ApiToken, User, utc_now
from webmonitor.schemas.api import ApiTokenView, Page
from webmonitor.security.auth import CurrentUser, require_owner
from webmonitor.services import accounts

ALL_SCOPES = frozenset({
    "read",
    "discover",
    "drafts:write",
    "drafts:approve",
    "monitors:write",
    "events:write",
})
DEFAULT_SCOPES = frozenset({
    "read",
    "discover",
    "drafts:write",
    "monitors:write",
    "events:write",
})
TOKEN_PREFIX = "wm_pat_"


@dataclass(frozen=True)
class TokenPrincipal:
    user: CurrentUser
    scopes: frozenset[str]
    token_id: UUID


def normalize_scopes(scopes: list[str] | set[str] | frozenset[str] | None) -> list[str]:
    """Validate and canonicalize PAT scopes; empty or unknown scopes are rejected."""
    if scopes is None:
        return sorted(DEFAULT_SCOPES)
    cleaned = [item.strip() for item in scopes if isinstance(item, str) and item.strip()]
    if not cleaned:
        raise DomainError("invalid_scope", 422, "At least one scope is required")
    unknown = sorted(set(cleaned) - ALL_SCOPES)
    if unknown:
        raise DomainError("invalid_scope", 422, "Unknown token scope",
                          details={"unknown": unknown})
    return sorted(set(cleaned))


def token_view(row: ApiToken) -> ApiTokenView:
    return ApiTokenView(
        id=row.id,
        name=row.name,
        token_prefix=row.token_prefix,
        scopes=list(row.scopes or []),
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


async def create_token(session: AsyncSession, user: CurrentUser, *, name: str,
                       scopes: list[str] | set[str] | frozenset[str] | None = None,
                       ttl_days: int | None = 90) -> tuple[ApiToken, str]:
    """Issue a PAT for `user`; the plaintext secret is returned once and never stored."""
    cleaned_name = name.strip()
    if not cleaned_name or len(cleaned_name) > 200:
        raise DomainError("validation_failed", 422, details={"fields": ["name"]})
    if ttl_days is not None and not 1 <= ttl_days <= 3650:
        raise DomainError("validation_failed", 422, details={"fields": ["ttl_days"]})
    normalized = normalize_scopes(scopes)
    raw = f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"
    now = utc_now()
    row = ApiToken(
        user_id=user.user_id,
        name=cleaned_name,
        token_prefix=raw[:16],
        token_hash=accounts.token_hash(raw),
        scopes=normalized,
        expires_at=now + timedelta(days=ttl_days) if ttl_days is not None else None,
    )
    session.add(row)
    await session.flush()
    return row, raw


async def list_tokens(session: AsyncSession, user: CurrentUser,
                      limit: int = 50, offset: int = 0) -> Page[ApiTokenView]:
    query = select(ApiToken).where(ApiToken.user_id == user.user_id)
    rows = (await session.scalars(
        query.order_by(ApiToken.created_at.desc(), ApiToken.id.desc())
        .limit(limit).offset(offset)
    )).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[ApiTokenView](items=[token_view(row) for row in rows], total=total or 0)


async def revoke_token(session: AsyncSession, user: CurrentUser, token_id: UUID) -> ApiToken:
    row = await session.scalar(
        select(ApiToken).where(ApiToken.id == token_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    require_owner(user, row)
    assert row is not None
    if row.revoked_at is None:
        row.revoked_at = utc_now()
        await session.flush()
    return row


async def resolve_token(session: AsyncSession, raw_token: str) -> TokenPrincipal:
    """Resolve an active, unrevoked, unexpired Bearer PAT into a TokenPrincipal."""
    if not raw_token.startswith(TOKEN_PREFIX) or len(raw_token) < len(TOKEN_PREFIX) + 16:
        raise DomainError("unauthenticated", 401)
    digest = accounts.token_hash(raw_token)
    now = utc_now()
    row = (await session.execute(
        select(ApiToken, User)
        .join(User, User.id == ApiToken.user_id)
        .where(ApiToken.token_hash == digest)
    )).one_or_none()
    if row is None:
        raise DomainError("unauthenticated", 401)
    token_row, user_row = row
    if token_row.revoked_at is not None or not user_row.active:
        raise DomainError("unauthenticated", 401)
    if token_row.expires_at is not None and token_row.expires_at <= now:
        raise DomainError("unauthenticated", 401)
    if token_row.last_used_at is None or (now - token_row.last_used_at) >= timedelta(seconds=60):
        token_row.last_used_at = now
        await session.commit()
    return TokenPrincipal(
        user=CurrentUser(user_id=user_row.id, role=user_row.role),
        scopes=frozenset(token_row.scopes or []),
        token_id=token_row.id,
    )


async def _user_by_email(session: AsyncSession, email: str) -> User:
    normalized = accounts.normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is None or not user.active:
        raise DomainError("not_found", 404, "Active user not found")
    return user


async def cli_create_token(session: AsyncSession, *, email: str, name: str,
                           scopes: list[str] | set[str] | frozenset[str] | None,
                           ttl_days: int | None) -> tuple[ApiToken, str]:
    user = await _user_by_email(session, email)
    row, raw = await create_token(
        session,
        CurrentUser(user_id=user.id, role=user.role),
        name=name,
        scopes=scopes,
        ttl_days=ttl_days,
    )
    await session.commit()
    return row, raw


async def cli_list_tokens(session: AsyncSession, *, email: str) -> list[ApiTokenView]:
    user = await _user_by_email(session, email)
    page = await list_tokens(session, CurrentUser(user_id=user.id, role=user.role),
                             limit=100, offset=0)
    return page.items


async def cli_revoke_token(session: AsyncSession, *, token_id: UUID) -> ApiToken:
    row = await session.scalar(
        select(ApiToken).where(ApiToken.id == token_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DomainError("not_found", 404)
    if row.revoked_at is None:
        row.revoked_at = utc_now()
    await session.commit()
    return row
