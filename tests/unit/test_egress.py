"""Public URL admission never replaces the connection-level proxy ACL."""
import pytest

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.security.egress import public_address, validate_url


@pytest.fixture(autouse=True)
def development_config(monkeypatch):
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    monkeypatch.setenv("SECRET_KEY", "x" * 40)
    monkeypatch.delenv("TARGET_POLICY", raising=False)
    monkeypatch.delenv("TARGET_ALLOWED_ORIGINS", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://169.254.169.254/", "http://[::1]/",
    "http://[::ffff:127.0.0.1]/", "http://10.0.0.1/", "http://172.16.0.1/",
    "http://192.168.1.1/", "http://224.0.0.1/", "http://localhost./",
    "http://a.localhost/", "file:///etc/passwd", "https://user:pass@example.com/",
    "http://example.com:8000/", "http://fixture:8000/", "http://host.docker.internal/",
    "http://[fe80::1%25eth0]/", "http://example.com\\@127.0.0.1/",
    "http://postgres/", "http://example.com:0/", "http://2130706433/",
])
def test_forbidden_targets(url):
    with pytest.raises(DomainError) as exc:
        validate_url(url)
    assert exc.value.code == "url_forbidden"


def test_public_targets_pass_with_fragment_removed():
    assert validate_url("https://example.com/pricing#top") == "https://example.com/pricing"


def test_mapped_ipv6_private_address_rejected():
    assert not public_address("::ffff:192.168.1.1")
    assert public_address("2606:4700:4700::1111")


def test_allowlist_exact_origin_allows_internal_fixture(monkeypatch):
    monkeypatch.setenv("TARGET_POLICY", "allowlist")
    monkeypatch.setenv("TARGET_ALLOWED_ORIGINS", "http://fixture:8000,http://mocksite:9000")
    get_settings.cache_clear()
    assert validate_url("http://fixture:8000/static/product") == "http://fixture:8000/static/product"
    assert validate_url("http://mocksite:9000/items") == "http://mocksite:9000/items"
    for url in ("http://fixture:8001/", "https://fixture:8000/", "http://127.0.0.1:8000/"):
        with pytest.raises(DomainError) as exc:
            validate_url(url)
        assert exc.value.code == "url_forbidden"
