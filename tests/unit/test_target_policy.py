"""Target policy is configuration, not a code branch per deployment."""
import pytest
from pydantic import ValidationError

from webmonitor.config import Settings, get_settings, parse_target_origins
from webmonitor.errors import DomainError
from webmonitor.security.egress import validate_url


def settings(**overrides) -> Settings:
    base = {"secret_key": "k" * 40, "app_origin": "https://monitor.example.com",
            "development_mode": False}
    return Settings(**{**base, **overrides})


@pytest.fixture(autouse=True)
def clean_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_public_policy_is_the_default():
    assert settings().target_policy == "public"
    assert parse_target_origins("") == frozenset()


@pytest.mark.parametrize("policy", ["allowlist", "any"])
def test_non_public_policy_requires_development_mode(policy):
    with pytest.raises(ValidationError):
        settings(target_policy=policy, target_allowed_origins="http://site:9000")


def test_allowlist_requires_origins():
    with pytest.raises(ValidationError):
        settings(target_policy="allowlist", development_mode=True)


@pytest.mark.parametrize("value", ["site:9000", "http://site:9000/path", "http://a:b@h:1"])
def test_malformed_allowlist_entries_are_rejected(value):
    with pytest.raises(ValidationError):
        settings(target_policy="allowlist", development_mode=True, target_allowed_origins=value)


def test_allowlist_policy_allows_only_listed_origins(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:8080")
    monkeypatch.setenv("TARGET_POLICY", "allowlist")
    monkeypatch.setenv("TARGET_ALLOWED_ORIGINS", "http://site:9000")
    get_settings.cache_clear()
    assert validate_url("http://site:9000/static/product") == "http://site:9000/static/product"
    for url in ("http://host.docker.internal:9000/", "http://postgres:5432/", "http://site:9001/"):
        with pytest.raises(DomainError) as raised:
            validate_url(url)
        assert raised.value.code == "url_forbidden"


def test_any_policy_allows_unlisted_targets_in_development(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:8080")
    monkeypatch.setenv("TARGET_POLICY", "any")
    get_settings.cache_clear()
    assert validate_url("http://host.docker.internal:9000/x") == "http://host.docker.internal:9000/x"


def test_secret_key_length_is_enforced():
    with pytest.raises(ValidationError):
        settings(secret_key="short")
