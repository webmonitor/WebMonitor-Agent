"""Unit tests run the host-side configuration convention: development settings."""
import pytest

from webmonitor.config import get_settings


@pytest.fixture(autouse=True)
def development_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret-key-at-least-32-bytes")
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    monkeypatch.setenv("APP_ORIGIN", "http://localhost:8080")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
