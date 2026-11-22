"""Registration consumes an invitation once; sessions resolve and revoke."""

from uuid import uuid4

import pytest
from sqlalchemy import select

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
    user = await accounts.create_user(
        session,
        email=f"{uuid4().hex}@example.com",
        password="correct horse battery",
        display_name="Owner",
        role="admin",
    )
    await session.commit()

    current, token = await accounts.login(
        session, email=user.email, password="correct horse battery", source_ip="127.0.0.1"
    )
    assert current.user_id == user.id and current.role == "admin"
    assert await accounts.resolve_session(session, token) == current

    await accounts.logout(session, token)
    with pytest.raises(DomainError) as raised:
        await accounts.resolve_session(session, token)
    assert raised.value.code == "unauthenticated"


@pytest.mark.asyncio
async def test_wrong_password_and_disabled_account_are_indistinguishable(session):
    user = await accounts.create_user(
        session,
        email=f"{uuid4().hex}@example.com",
        password="correct horse battery",
        display_name="Owner",
    )
    await session.commit()

    with pytest.raises(DomainError) as wrong:
        await accounts.login(
            session, email=user.email, password="wrong password here", source_ip="127.0.0.1"
        )
    assert wrong.value.code == "invalid_credentials"

    user.active = False
    await session.commit()
    with pytest.raises(DomainError) as disabled:
        await accounts.login(
            session, email=user.email, password="correct horse battery", source_ip="127.0.0.1"
        )
    assert disabled.value.code == "invalid_credentials"


@pytest.mark.asyncio
async def test_repeated_failures_hit_the_login_throttle(session):
    email = f"{uuid4().hex}@example.com"
    for _ in range(10):
        with pytest.raises(DomainError):
            await accounts.login(
                session, email=email, password="wrong password here", source_ip="10.0.0.9"
            )
    with pytest.raises(DomainError) as raised:
        await accounts.login(
            session, email=email, password="wrong password here", source_ip="10.0.0.9"
        )
    assert raised.value.code == "rate_limited"
    assert raised.value.status == 429
    assert raised.value.details["retry_after"] >= 1


@pytest.mark.asyncio
async def test_invitation_registers_once_and_requires_the_matching_email(session):
    await accounts.create_user(
        session,
        email=f"admin-{uuid4().hex}@example.com",
        password="correct horse battery",
        display_name="Admin",
        role="admin",
    )
    await session.commit()
    invitee = f"{uuid4().hex}@example.com"
    url = await accounts.invite_create(session, email=invitee, ttl_hours=1)
    token = url.split("invitation_token=")[1].split("&")[0]

    with pytest.raises(DomainError) as mismatch:
        await accounts.register(
            session,
            display_name="Someone",
            email=f"{uuid4().hex}@example.com",
            password="correct horse battery",
            invitation_token=token,
        )
    assert mismatch.value.code == "registration_failed"

    current, session_token = await accounts.register(
        session,
        display_name="Invitee",
        email=invitee,
        password="correct horse battery",
        invitation_token=token,
    )
    assert current.role == "member"
    assert await accounts.resolve_session(session, session_token) == current

    with pytest.raises(DomainError) as reused:
        await accounts.register(
            session,
            display_name="Invitee",
            email=invitee,
            password="correct horse battery",
            invitation_token=token,
        )
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


@pytest.mark.asyncio
async def test_deactivation_stops_owned_work_and_reactivation_does_not_backfill(session):
    from support import seed_owner
    from test_runs import make_monitor, result, running_job

    from webmonitor.models import Delivery, Event, Job, Monitor, Snapshot, utc_now
    from webmonitor.models import Session as LoginSession
    from webmonitor.services import jobs, notifications, runs

    user, _, group = await seed_owner(session)
    monitor = await make_monitor(session, user, group)
    queued = await jobs.enqueue(
        session,
        user_id=user.id,
        kind="production",
        monitor_id=monitor.id,
        revision=monitor.spec_version,
        url=monitor.url,
        spec=monitor.spec,
    )
    running = Job(
        user_id=user.id,
        kind="agent",
        status="running",
        lease_owner="worker",
        lease_expires_at=utc_now(),
        attempt_count=1,
    )
    login = LoginSession(user_id=user.id, token_hash="a" * 64, expires_at=utc_now())
    session.add_all([running, login])
    await session.flush()
    event = Event(monitor_id=monitor.id, job_id=queued.id, type="content_changed", change={})
    session.add(event)
    await session.flush()
    deliveries = [
        Delivery(
            user_id=user.id,
            monitor_id=monitor.id,
            event_id=event.id,
            channel="email",
            recipient=recipient,
            subject="Alert",
            body_text="x",
            payload={"recipient_sources": [str(group.id)]},
            status=status,
            lease_owner="mailer" if status == "sending" else None,
            available_at=utc_now(),
        )
        for recipient, status in (
            ("ops@example.com", "queued"),
            ("retry@example.com", "retrying"),
            ("sending@example.com", "sending"),
        )
    ]
    session.add_all(deliveries)
    await session.commit()
    assert await notifications.authorized(session, deliveries[0])

    await accounts.set_availability(session, user, False)
    await session.commit()
    assert not user.active
    assert monitor.status == "paused" and monitor.paused_at is not None
    assert queued.status == "cancelled"
    assert running.status == "running" and running.cancel_requested_at is not None
    persisted_login = await session.get(LoginSession, login.id, populate_existing=True)
    assert persisted_login.revoked_at is not None
    for row in deliveries:
        await session.refresh(row)
    assert all(row.status == "cancelled" and row.cancelled_at is not None for row in deliveries)
    assert all(row.lease_owner is None for row in deliveries)
    assert not await notifications.authorized(session, deliveries[0])

    await accounts.set_availability(session, user, True)
    await session.commit()
    assert user.active and monitor.status == "paused"
    assert await runs.schedule_due(session) == 0
    assert queued.status == "cancelled" and running.cancel_requested_at is not None

    # Even a conflicting direct status write cannot bypass the owner-active fences.
    await accounts.set_availability(session, user, False)
    monitor.status = "active"
    await session.commit()
    assert await runs.schedule_due(session) == 0
    in_flight = await running_job(session, monitor)
    assert await runs.commit_success(session, in_flight, result("changed")) is False
    await session.commit()
    assert in_flight.status == "discarded"
    assert await session.scalar(select(Snapshot).where(Snapshot.job_id == in_flight.id)) is None
    failed = await running_job(session, monitor)
    assert (
        await runs.fail_run(session, failed, error_code="target_unavailable", retryable=True)
        is True
    )
    assert failed.status == "discarded"
    stored_monitor = await session.get(Monitor, monitor.id)
    assert stored_monitor.baseline_snapshot_id is None
    assert stored_monitor.health_status == "healthy"


@pytest.mark.asyncio
async def test_concurrent_database_initialization_creates_only_one_admin(session, monkeypatch):
    import asyncio

    from sqlalchemy import func

    from webmonitor.config import get_settings
    from webmonitor.db import initialize_database
    from webmonitor.storage import evidence

    email = f"admin-{uuid4().hex}@example.com"
    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", "correct horse battery")
    get_settings.cache_clear()

    async def bucket_ready():
        return None

    monkeypatch.setattr(evidence, "initialize_bucket", bucket_ready)
    try:
        await asyncio.gather(initialize_database(), initialize_database())
        assert await session.scalar(select(func.count()).select_from(User)) == 1
        admin = await session.scalar(select(User).where(User.email == email))
        assert admin is not None and admin.role == "admin" and admin.active
    finally:
        get_settings.cache_clear()
