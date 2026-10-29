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
