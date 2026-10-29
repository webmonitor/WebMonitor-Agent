"""Registration consumes an invitation once; sessions resolve and revoke."""
from uuid import uuid4

import pytest

from webmonitor.errors import DomainError
from webmonitor.models import User
from webmonitor.services import accounts


@pytest.fixture(autouse=True)
def fresh_throttle():
    accounts.reset_login_attempts()
    yield
    accounts.reset_login_attempts()


@pytest.mark.asyncio
async def test_login_issues_a_session_that_resolves_and_revokes(session):
    user = await accounts.create_user(session, email=f"{uuid4().hex}@example.com",
        password="correct horse battery", display_name="Owner", role="admin")
    await session.commit()

    current, token = await accounts.login(session, email=user.email,
        password="correct horse battery", source_ip="127.0.0.1")
    assert current.user_id == user.id and current.role == "admin"
    assert await accounts.resolve_session(session, token) == current

    await accounts.logout(session, token)
    with pytest.raises(DomainError) as raised:
        await accounts.resolve_session(session, token)
    assert raised.value.code == "unauthenticated"


@pytest.mark.asyncio
async def test_wrong_password_and_disabled_account_are_indistinguishable(session):
    user = await accounts.create_user(session, email=f"{uuid4().hex}@example.com",
        password="correct horse battery", display_name="Owner")
    await session.commit()

    with pytest.raises(DomainError) as wrong:
        await accounts.login(session, email=user.email, password="wrong password here",
                             source_ip="127.0.0.1")
    assert wrong.value.code == "invalid_credentials"

    user.active = False
    await session.commit()
    with pytest.raises(DomainError) as disabled:
        await accounts.login(session, email=user.email, password="correct horse battery",
                             source_ip="127.0.0.1")
    assert disabled.value.code == "invalid_credentials"


@pytest.mark.asyncio
async def test_repeated_failures_hit_the_login_throttle(session):
    email = f"{uuid4().hex}@example.com"
    for _ in range(10):
        with pytest.raises(DomainError):
            await accounts.login(session, email=email, password="wrong password here",
                                 source_ip="10.0.0.9")
    with pytest.raises(DomainError) as raised:
        await accounts.login(session, email=email, password="wrong password here",
                             source_ip="10.0.0.9")
    assert raised.value.code == "rate_limited"
    assert raised.value.status == 429
    assert raised.value.details["retry_after"] >= 1


@pytest.mark.asyncio
async def test_invitation_registers_once_and_requires_the_matching_email(session):
    await accounts.create_user(session, email=f"admin-{uuid4().hex}@example.com",
        password="correct horse battery", display_name="Admin", role="admin")
    await session.commit()
    invitee = f"{uuid4().hex}@example.com"
    url = await accounts.invite_create(session, email=invitee, ttl_hours=1)
    token = url.split("invitation_token=")[1].split("&")[0]

    with pytest.raises(DomainError) as mismatch:
        await accounts.register(session, display_name="Someone", email=f"{uuid4().hex}@example.com",
            password="correct horse battery", invitation_token=token)
    assert mismatch.value.code == "registration_failed"

    current, session_token = await accounts.register(session, display_name="Invitee",
        email=invitee, password="correct horse battery", invitation_token=token)
    assert current.role == "member"
    assert await accounts.resolve_session(session, session_token) == current

    with pytest.raises(DomainError) as reused:
        await accounts.register(session, display_name="Invitee", email=invitee,
            password="correct horse battery", invitation_token=token)
    assert reused.value.code == "registration_failed"


@pytest.mark.asyncio
async def test_admin_creation_is_single_use(session):
    email = f"{uuid4().hex}@example.com"
    created = await accounts.admin_create(session, email=email, password="correct horse battery")
    assert created.role == "admin"
    assert (await session.get(User, created.user_id)).role == "admin"

    with pytest.raises(DomainError) as conflict:
        await accounts.admin_create(session, email=email, password="correct horse battery")
    assert conflict.value.code == "account_exists"
