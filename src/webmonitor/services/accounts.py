"""Identity, invitation consumption, sessions and process-local login throttling."""
import asyncio
import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Literal
from urllib.parse import urlencode
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.models import Invitation, Session, User, utc_now
from webmonitor.schemas.api import InvitationView, Page
from webmonitor.security.auth import CurrentUser

_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))
# Password hashing is memory-hard; unbounded concurrency is a denial-of-service lever.
_hash_slots = asyncio.Semaphore(2)
_attempts: dict[str, deque[float]] = defaultdict(deque)
_PRUNE_THRESHOLD = 4096


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


async def _hash(password: str) -> str:
    async with _hash_slots:
        return await asyncio.to_thread(_hasher.hash, password)


async def _verify(hashed: str, password: str) -> bool:
    async with _hash_slots:
        try:
            return await asyncio.to_thread(_hasher.verify, hashed, password)
        except (VerificationError, InvalidHashError):
            return False


def reset_login_attempts() -> None:
    """Tests and administrative diagnostics may clear the in-process window."""
    _attempts.clear()


def _buckets(email: str, source_ip: str) -> list[tuple[str, int]]:
    """One address, one account and one client: each needs its own ceiling."""
    settings = get_settings()
    return [
        (f"pair|{email}|{source_ip}", settings.login_attempts),
        (f"acct|{email}", settings.login_attempts * 2),
        (f"ip|{source_ip}", settings.login_attempts * 5),
    ]


def _prune(now: float, window: float) -> None:
    if len(_attempts) <= _PRUNE_THRESHOLD:
        return
    for key in [key for key, recent in _attempts.items()
                if not recent or now - recent[-1] > window]:
        del _attempts[key]


def _throttle(email: str, source_ip: str) -> None:
    settings = get_settings()
    now = time.monotonic()
    window = settings.login_window_minutes * 60
    for key, limit in _buckets(email, source_ip):
        recent = _attempts[key]
        while recent and now - recent[0] > window:
            recent.popleft()
        if len(recent) >= limit:
            retry_after = max(1, int(window - (now - recent[0])) + 1)
            raise DomainError("rate_limited", 429, details={"retry_after": retry_after})


def _record_failure(email: str, source_ip: str) -> None:
    now = time.monotonic()
    for key, _ in _buckets(email, source_ip):
        _attempts[key].append(now)
    _prune(now, get_settings().login_window_minutes * 60)


def _clear_attempts(email: str, source_ip: str) -> None:
    _attempts.pop(f"pair|{email}|{source_ip}", None)
    _attempts.pop(f"acct|{email}", None)


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
        password_hash=await _hash(password), role=role)
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


async def create_invitation(session: AsyncSession, *, email: str, ttl_hours: int,
                            created_by_user_id: UUID) -> tuple[Invitation, str]:
    email = normalize_email(email)
    settings = get_settings()
    if settings.allowed_registration_emails and email not in settings.allowed_registration_emails:
        raise DomainError("email_not_allowed", 403)
    if not 1 <= ttl_hours <= 168:
        raise DomainError("invalid_invitation_ttl", 422)
    # A reissued invitation replaces the previous link for the same address.
    await session.execute(update(Invitation).where(Invitation.email == email,
        Invitation.consumed_at.is_(None)).values(consumed_at=utc_now()))
    token = secrets.token_urlsafe(32)
    invitation = Invitation(email=email, token_hash=token_hash(token),
        created_by_user_id=created_by_user_id,
        expires_at=utc_now() + timedelta(hours=ttl_hours))
    session.add(invitation)
    await session.flush()
    url = settings.app_origin + "/register?" + urlencode(
        {"invitation_token": token, "email": email})
    return invitation, url


async def invite_create(session: AsyncSession, *, email: str, ttl_hours: int = 24) -> str:
    admin = await session.scalar(select(User).where(User.role == "admin", User.active.is_(True))
        .order_by(User.created_at).limit(1))
    if admin is None:
        raise DomainError("administrator_required", 409)
    _, url = await create_invitation(session, email=email, ttl_hours=ttl_hours,
                                     created_by_user_id=admin.id)
    await session.commit()
    return url


async def list_invitations(session: AsyncSession, limit: int,
                           offset: int) -> Page[InvitationView]:
    query = select(Invitation).where(Invitation.consumed_at.is_(None),
                                     Invitation.expires_at > utc_now())
    rows = (await session.scalars(query.order_by(Invitation.created_at.desc(),
        Invitation.id.desc()).limit(limit).offset(offset))).all()
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return Page[InvitationView](items=[
        InvitationView(id=row.id, email=row.email, created_at=row.created_at,
                       expires_at=row.expires_at, consumed_at=row.consumed_at)
        for row in rows
    ], total=total or 0)


async def register(session: AsyncSession, *, display_name: str, email: str, password: str,
                   invitation_token: str) -> tuple[CurrentUser, str]:
    """Validate the invitation before spending a memory-hard hash on it."""
    try:
        email = normalize_email(email)
        validate_password(password)
        if not display_name.strip() or len(display_name) > 200:
            raise DomainError("registration_failed", 422)
    except DomainError:
        raise DomainError("registration_failed", 422) from None
    invitation = await session.scalar(select(Invitation).where(
        Invitation.token_hash == token_hash(invitation_token)).with_for_update())
    if (invitation is None or invitation.consumed_at is not None
            or invitation.expires_at <= utc_now() or invitation.email != email):
        raise DomainError("registration_failed", 409)
    if await session.scalar(select(User.id).where(User.email == email)) is not None:
        raise DomainError("registration_failed", 409)
    hashed = await _hash(password)
    user = User(email=email, display_name=display_name.strip(), password_hash=hashed,
                role="member")
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError("registration_failed", 409) from None
        raise
    invitation.consumed_at = utc_now()
    token = _new_session(session, user)
    await session.commit()
    return CurrentUser(user_id=user.id, role=user.role), token


async def login(session: AsyncSession, *, email: str, password: str,
                source_ip: str) -> tuple[CurrentUser, str]:
    email = email.strip().casefold()
    _throttle(email, source_ip)
    user = await session.scalar(select(User).where(User.email == email))
    valid = await _verify(user.password_hash if user else _dummy_hash, password)
    if not valid or user is None or not user.active:
        _record_failure(email, source_ip)
        raise DomainError("invalid_credentials", 401)
    _clear_attempts(email, source_ip)
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


async def logout(session: AsyncSession, token: str | None) -> None:
    """An unknown or already revoked token still ends the browser's session."""
    if token:
        row = await session.scalar(select(Session).where(
            Session.token_hash == token_hash(token)).with_for_update())
        if row is not None and row.revoked_at is None:
            row.revoked_at = utc_now()
    await session.commit()


async def purge_expired_sessions(session: AsyncSession) -> int:
    """Expired rows are dead weight; the table has no other reaper."""
    result = await session.execute(delete(Session).where(Session.expires_at < utc_now()))
    return result.rowcount or 0
