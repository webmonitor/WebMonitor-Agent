"""Identity input normalization happens before any database write."""
import pytest

from webmonitor.errors import DomainError
from webmonitor.services import accounts


def test_email_is_normalized_and_invalid_input_is_rejected():
    assert accounts.normalize_email("  Owner@Example.COM ") == "owner@example.com"
    for value in ("", "not-an-email", "a@", "@example.com"):
        with pytest.raises(DomainError) as raised:
            accounts.normalize_email(value)
        assert raised.value.code == "invalid_email"


@pytest.mark.parametrize("password", ["", "short", "x" * 11, "x" * 129])
def test_password_length_is_enforced(password):
    with pytest.raises(DomainError) as raised:
        accounts.validate_password(password)
    assert raised.value.code == "invalid_password"


@pytest.mark.parametrize("password", ["x" * 12, "correct horse battery", "x" * 128])
def test_acceptable_passwords_pass(password):
    assert accounts.validate_password(password) is None


def test_session_tokens_are_hashed_not_stored():
    digest = accounts.token_hash("token-value")
    assert len(digest) == 64
    assert digest == accounts.token_hash("token-value")
    assert digest != accounts.token_hash("other-value")


@pytest.mark.asyncio
async def test_an_invalid_invitation_costs_no_password_hash(monkeypatch):
    """Cheap rejection: a bad token must not buy an attacker an Argon2 run."""
    hashed: list[str] = []

    async def counting(password: str) -> str:
        hashed.append(password)
        return "hash"

    class NoInvitation:
        async def scalar(self, *args, **kwargs):
            return None

    monkeypatch.setattr(accounts, "_hash", counting)
    with pytest.raises(DomainError) as rejected:
        await accounts.register(NoInvitation(), display_name="Member",
                                email="member@example.com",
                                password="correct horse battery", invitation_token="bad")
    assert rejected.value.code == "registration_failed"
    assert hashed == []


def test_login_buckets_scale_with_the_configured_attempt_limit(monkeypatch):
    from webmonitor.config import get_settings

    monkeypatch.setenv("LOGIN_ATTEMPTS", "4")
    get_settings.cache_clear()
    try:
        assert accounts._buckets("a@example.com", "1.2.3.4") == [
            ("pair|a@example.com|1.2.3.4", 4), ("acct|a@example.com", 8),
            ("ip|1.2.3.4", 20)]
    finally:
        get_settings.cache_clear()


def test_an_account_bucket_blocks_a_new_address(monkeypatch):
    """A distributed guess against one account is throttled regardless of source."""
    from webmonitor.config import get_settings

    monkeypatch.setenv("LOGIN_ATTEMPTS", "2")
    get_settings.cache_clear()
    try:
        accounts.reset_login_attempts()
        for index in range(4):
            accounts._record_failure("target@example.com", f"10.0.0.{index}")
        with pytest.raises(DomainError) as blocked:
            accounts._throttle("target@example.com", "10.0.0.9")
        assert blocked.value.code == "rate_limited"
    finally:
        accounts.reset_login_attempts()
        get_settings.cache_clear()


def test_a_successful_login_clears_the_pair_and_account_buckets():
    accounts.reset_login_attempts()
    accounts._record_failure("owner@example.com", "10.0.0.1")
    accounts._clear_attempts("owner@example.com", "10.0.0.1")
    assert "pair|owner@example.com|10.0.0.1" not in accounts._attempts
    assert "acct|owner@example.com" not in accounts._attempts


def test_readiness_derives_its_table_list_from_the_model():
    from webmonitor.db import EXPECTED_TABLES

    assert "email_templates" in EXPECTED_TABLES
    assert "email_deliveries" in EXPECTED_TABLES
