"""Identity, invitation consumption, sessions and process-local login throttling."""
import asyncio
import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Literal
from urllib.parse import urlencode

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Invitation, Session, User, utc_now
from webmonitor.security.auth import CurrentUser

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))
_attempts: dict[str, deque[float]] = defaultdict(deque)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(value: str) -> str:
    email = value.strip().casefold()
    try:
        validate_email(email, check_deliverability=False)
    except EmailNotValidError:
        raise DomainError("invalid_email", 422) from None
    return email


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise DomainError("invalid_password", 422, "Password must contain 12–128 characters")


def reset_login_attempts() -> None:
    """Tests and administrative diagnostics may clear the in-process window."""
    _attempts.clear()


def _throttle(email: str, source_ip: str) -> None:
    settings = get_settings()
    now = time.monotonic()
    window = settings.login_window_minutes * 60
    for key in (f"{email}|{source_ip}", f"ip|{source_ip}"):
        recent = _attempts[key]
        while recent and now - recent[0] > window:
            recent.popleft()
        if len(recent) >= settings.login_attempts:
            retry_after = max(1, int(window - (now - recent[0])) + 1)
            raise DomainError("rate_limited", 429, details={"retry_after": retry_after})


def _record_failure(email: str, source_ip: str) -> None:
    now = time.monotonic()
    _attempts[f"{email}|{source_ip}"].append(now)
    _attempts[f"ip|{source_ip}"].append(now)


def _new_session(session: AsyncSession, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(Session(user_id=user.id, token_hash=token_hash(token),
        expires_at=utc_now() + timedelta(hours=get_settings().session_ttl_hours)))
    return token


async def create_user(session: AsyncSession, *, email: str, password: str, display_name: str,
                      role: Literal["admin", "member"] = "member") -> User:
    email = normalize_email(email)
    validate_password(password)
    user = User(email=email, display_name=display_name.strip() or email,
        password_hash=await asyncio.to_thread(_hasher.hash, password), role=role)
    session.add(user)
    await session.flush()
    return user


async def admin_create(session: AsyncSession, *, email: str, password: str) -> CurrentUser:
    if await session.scalar(select(User.id).where(User.email == normalize_email(email))) is not None:
        raise DomainError("account_exists", 409)
    user = await create_user(session, email=email, password=password, display_name=email,
                             role="admin")
    await session.commit()
    return CurrentUser(user_id=user.id, role="admin")


async def invite_create(session: AsyncSession, *, email: str, ttl_hours: int = 24) -> str:
    email = normalize_email(email)
    settings = get_settings()
    if settings.allowed_registration_emails and email not in settings.allowed_registration_emails:
        raise DomainError("email_not_allowed", 403)
    if not 1 <= ttl_hours <= 168:
        raise DomainError("invalid_invitation_ttl", 422)
    token = secrets.token_urlsafe(32)
    admin = await session.scalar(select(User).where(User.role == "admin", User.active.is_(True))
        .order_by(User.created_at).limit(1))
    if admin is None:
        raise DomainError("administrator_required", 409)
    session.add(Invitation(email=email, token_hash=token_hash(token),
        created_by_user_id=admin.id, expires_at=utc_now() + timedelta(hours=ttl_hours)))
    await session.commit()
    return settings.app_origin + "/register?" + urlencode({"invitation_token": token, "email": email})


async def register(session: AsyncSession, *, display_name: str, email: str, password: str,
                   invitation_token: str) -> tuple[CurrentUser, str]:
    try:
        email = normalize_email(email)
        validate_password(password)
        if not display_name.strip() or len(display_name) > 200:
            raise DomainError("registration_failed", 422)
    except DomainError:
        raise DomainError("registration_failed", 422) from None
    hashed = await asyncio.to_thread(_hasher.hash, password)
    invitation = await session.scalar(select(Invitation).where(
        Invitation.token_hash == token_hash(invitation_token)).with_for_update())
    if (invitation is None or invitation.consumed_at is not None
            or invitation.expires_at <= utc_now() or invitation.email != email):
        raise DomainError("registration_failed", 409)
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise DomainError("registration_failed", 409)
    user = User(email=email, display_name=display_name.strip(), password_hash=hashed,
                role="member")
    session.add(user)
    await session.flush()
    invitation.consumed_at = utc_now()
    token = _new_session(session, user)
    await session.commit()
    return CurrentUser(user_id=user.id, role=user.role), token


async def login(session: AsyncSession, *, email: str, password: str,
                source_ip: str) -> tuple[CurrentUser, str]:
    email = email.strip().casefold()
    _throttle(email, source_ip)
    user = await session.scalar(select(User).where(User.email == email))
    try:
        valid = await asyncio.to_thread(_hasher.verify,
            user.password_hash if user else _dummy_hash, password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or user is None or not user.active:
        _record_failure(email, source_ip)
        raise DomainError("invalid_credentials", 401)
    token = _new_session(session, user)
    await session.commit()
    return CurrentUser(user_id=user.id, role=user.role), token


async def resolve_session(session: AsyncSession, token: str) -> CurrentUser:
    row = await session.scalar(select(User).join(Session, Session.user_id == User.id).where(
        Session.token_hash == token_hash(token), Session.revoked_at.is_(None),
        Session.expires_at > utc_now(), User.active.is_(True)))
    if row is None:
        raise DomainError("unauthenticated", 401)
    return CurrentUser(user_id=row.id, role=row.role)


async def logout(session: AsyncSession, token: str) -> None:
    row = await session.scalar(select(Session).where(
        Session.token_hash == token_hash(token)).with_for_update())
    if row is not None:
        row.revoked_at = utc_now()
    await session.commit()
