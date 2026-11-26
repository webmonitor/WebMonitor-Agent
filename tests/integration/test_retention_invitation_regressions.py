"""Protected retention prefixes and invitation replacement cannot starve or race."""
import asyncio
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from test_retention_gc import evidence, terminal_job, user_for
from webmonitor.config import get_settings
from webmonitor.models import Conversation, Draft, Invitation, Job, User, utc_now
from webmonitor.services import accounts, retention


@pytest.fixture
def retention_settings(monkeypatch):
    monkeypatch.setenv("RETENTION_DAYS", "30")
    monkeypatch.setenv("RETENTION_GC_BATCH_SIZE", "100")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_gc_keyset_scans_past_a_fully_protected_prefix(
        session, monkeypatch, retention_settings):
    user = await user_for(session)
    conversation = Conversation(user_id=user.id, title="Protected previews")
    session.add(conversation)
    await session.flush()
    draft = Draft(user_id=user.id, conversation_id=conversation.id, spec_revision=1)
    session.add(draft)
    await session.flush()

    old = utc_now() - timedelta(days=60)
    protected_ids = set()
    protected_refs = []
    for index in range(100):
        ref = evidence(f"protected-prefix-{index}")
        protected_refs.append(ref)
        job = await terminal_job(session, user, old + timedelta(microseconds=index), ref,
                                 kind="preview", draft_id=draft.id)
        protected_ids.add(job.id)
    draft.extraction_preview = {"evidence_refs": protected_refs}
    unprotected_ref = evidence("after-protected-prefix")
    unprotected = await terminal_job(session, user, old + timedelta(seconds=1),
                                     unprotected_ref)
    await session.commit()

    deleted = []

    async def remove(bucket, key):
        deleted.append((bucket, key))

    monkeypatch.setattr(retention, "delete_evidence", remove)
    stats = await retention.collect(session)

    assert stats.jobs_deleted == 1
    assert stats.evidence_deleted == 1 and stats.failures == 0
    assert deleted == [("evidence", unprotected_ref["object_key"])]
    assert await session.get(Job, unprotected.id) is None
    remaining_protected = await session.scalars(select(Job.id).where(Job.id.in_(protected_ids)))
    assert set(remaining_protected) == protected_ids


@pytest.mark.asyncio
async def test_concurrent_normalized_invitations_leave_only_one_live_link(session):
    admin = User(email=f"admin-{uuid4().hex}@example.com", display_name="Admin",
                 password_hash="not-a-login-hash", role="admin")
    session.add(admin)
    await session.commit()
    factory = async_sessionmaker(session.bind, expire_on_commit=False)
    start = asyncio.Event()

    async def issue(email: str) -> str:
        await start.wait()
        async with factory() as worker:
            _, url = await accounts.create_invitation(
                worker, email=email, ttl_hours=24, created_by_user_id=admin.id)
            await worker.commit()
        return parse_qs(urlparse(url).query)["invitation_token"][0]

    normalized = f"invitee-{uuid4().hex}@example.com"
    local, domain = normalized.split("@")
    variants = [
        normalized,
        f" {local.upper()}@{domain} ",
        f"{local.capitalize()}@{domain.upper()}",
        f"\t{local.upper()}@{domain.upper()}\n",
    ]
    tasks = [asyncio.create_task(issue(variant)) for variant in variants]
    start.set()
    tokens = await asyncio.gather(*tasks)

    rows = list((await session.scalars(select(Invitation).where(
        Invitation.email == normalized))).all())
    assert len(rows) == len(variants)
    assert len(set(tokens)) == len(variants)
    live = [row for row in rows if row.consumed_at is None]
    assert len(live) == 1
    live_hash = live[0].token_hash
    assert sum(accounts.token_hash(token) == live_hash for token in tokens) == 1
    assert all(row.email == normalized for row in rows)
