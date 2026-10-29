"""Authentication always resolves identity from the server-side session record."""
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.db import session_dependency
from webmonitor.errors import DomainError
from webmonitor.security.auth import CurrentUser
from webmonitor.services import accounts

SESSION_COOKIE = "wm_session"
DatabaseSession = Annotated[AsyncSession, Depends(session_dependency)]


async def current_user(request: Request, session: DatabaseSession) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise DomainError("unauthenticated", status=401)
    return await accounts.resolve_session(session, token)


AuthenticatedUser = Annotated[CurrentUser, Depends(current_user)]
