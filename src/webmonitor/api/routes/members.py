"""Single-deployment user administration."""
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from webmonitor.api.dependencies import AuthenticatedUser, DatabaseSession
from webmonitor.errors import DomainError
from webmonitor.models import Session, User, utc_now
from webmonitor.schemas.api import Availability, Member, Page
from webmonitor.security.auth import require_admin

router = APIRouter(prefix="/api/v1/members", tags=["members"])


def _view(user: User) -> Member:
    return Member(id=user.id, email=user.email, display_name=user.display_name,
                  role=user.role, active=user.active, created_at=user.created_at)


@router.get("", response_model=Page[Member])
async def list_members(session: DatabaseSession, user: AuthenticatedUser,
                       limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    require_admin(user)
    rows = (await session.scalars(select(User).order_by(User.created_at.desc())
        .limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(User))
    return Page[Member](items=[_view(row) for row in rows], total=total or 0)


@router.patch("/{user_id}", response_model=Member)
async def set_availability(user_id: UUID, body: Availability, session: DatabaseSession,
                           user: AuthenticatedUser):
    require_admin(user)
    row = await session.scalar(select(User).where(User.id == user_id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise DomainError("not_found", 404)
    if row.id == user.user_id and not body.active:
        raise DomainError("cannot_disable_self", 409)
    row.active = body.active
    if not body.active:
        await session.execute(update(Session).where(Session.user_id == row.id,
            Session.revoked_at.is_(None)).values(revoked_at=utc_now()))
    result = _view(row)
    await session.commit()
    return result
