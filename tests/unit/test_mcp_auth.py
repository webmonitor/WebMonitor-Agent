"""Unit tests for MCP PAT scopes, Origin validation, error redaction and payload bounds."""
from uuid import uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from webmonitor.config import Settings, get_settings
from webmonitor.errors import DomainError
from webmonitor.mcp.auth import (
    _principal_var,
    extract_bearer_token,
    require_principal,
    validate_mcp_origin,
)
from webmonitor.mcp.errors import bound_untrusted_json, coerce_spec_input, safe_mcp_error
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.security.auth import CurrentUser
from webmonitor.services.tokens import ALL_SCOPES, DEFAULT_SCOPES, TokenPrincipal, normalize_scopes


def _make_request(*, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
    }
    return Request(scope)


def test_scope_normalization_and_defaults():
    assert normalize_scopes(None) == sorted(DEFAULT_SCOPES)
    assert "drafts:approve" not in DEFAULT_SCOPES
    assert "drafts:approve" in ALL_SCOPES
    assert normalize_scopes([" read ", "discover", "read"]) == ["discover", "read"]
    with pytest.raises(DomainError) as empty:
        normalize_scopes([])
    assert empty.value.code == "invalid_scope"
    with pytest.raises(DomainError) as unknown:
        normalize_scopes(["read", "admin:root"])
    assert unknown.value.code == "invalid_scope"
    assert unknown.value.details == {"unknown": ["admin:root"]}


def test_require_principal_enforces_scope():
    with pytest.raises(DomainError) as missing:
        require_principal("read")
    assert missing.value.code == "unauthenticated"

    principal = TokenPrincipal(
        user=CurrentUser(user_id=uuid4(), role="member"),
        scopes=frozenset({"read", "discover"}),
        token_id=uuid4(),
    )
    tok = _principal_var.set(principal)
    try:
        assert require_principal("read") == principal
        with pytest.raises(DomainError) as denied:
            require_principal("drafts:approve")
        assert denied.value.code == "insufficient_scope"
        assert denied.value.status == 403
    finally:
        _principal_var.reset(tok)


def test_mcp_origin_validation(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://studio.example.com")
    get_settings.cache_clear()

    validate_mcp_origin(_make_request())
    validate_mcp_origin(_make_request(headers=[(b"origin", b"http://localhost:8080")]))
    validate_mcp_origin(_make_request(headers=[(b"origin", b"https://studio.example.com")]))

    with pytest.raises(DomainError) as bad:
        validate_mcp_origin(_make_request(headers=[(b"origin", b"https://evil.example")]))
    assert bad.value.code == "origin_invalid"
    assert bad.value.status == 403

    with pytest.raises(DomainError) as dup:
        validate_mcp_origin(_make_request(headers=[
            (b"origin", b"http://localhost:8080"),
            (b"origin", b"http://localhost:8080"),
        ]))
    assert dup.value.code == "origin_invalid"


def test_extract_bearer_token_rejects_cookies_and_malformed_headers():
    with pytest.raises(DomainError) as missing:
        extract_bearer_token(_make_request(headers=[(b"cookie", b"wm_session=secret")]))
    assert missing.value.code == "unauthenticated"

    with pytest.raises(DomainError) as basic:
        extract_bearer_token(_make_request(headers=[(b"authorization", b"Basic abc")]))
    assert basic.value.code == "unauthenticated"

    assert extract_bearer_token(
        _make_request(headers=[(b"authorization", b"bearer wm_pat_123456")])
    ) == "wm_pat_123456"


def test_safe_mcp_error_redacts_internal_exceptions():
    redacted = safe_mcp_error(RuntimeError("postgres password=secret"))
    assert redacted["error"]["code"] == "tool_failed"
    assert "secret" not in redacted["error"]["message"]

    domain = safe_mcp_error(DomainError("stale_revision", 409, "Stale", details={"rev": 2}))
    assert domain == {"error": {"code": "stale_revision", "message": "Stale", "details": {"rev": 2}}}

    try:
        MonitorSpec.model_validate({"name": "bad"})
    except ValidationError as exc:
        val = safe_mcp_error(exc, is_spec=True)
        assert val["error"]["code"] == "validation_failed"
        assert isinstance(val["error"]["details"], list) and val["error"]["details"]


def test_coerce_spec_input_and_bound_untrusted_json():
    with pytest.raises(ValueError):
        coerce_spec_input("{not json")

    small = bound_untrusted_json({"price": "10.00"}, max_bytes=1024)
    assert small == {"untrusted": True, "truncated": False, "data": {"price": "10.00"}, "untrusted_summary": None}

    big = bound_untrusted_json({"text": "x" * 500}, max_bytes=64, label="summary")
    assert big["untrusted"] is True
    assert big["truncated"] is True
    assert big["data"] is None
    assert len(big["summary"]) <= 64


def test_settings_validate_mcp_origins_and_analyze_quota():
    with pytest.raises(ValidationError):
        Settings(
            secret_key="k" * 40,
            app_origin="https://monitor.example.com",
            mcp_allowed_origins="https://bad.example.com/path",
        )
    with pytest.raises(ValidationError):
        Settings(
            secret_key="k" * 40,
            app_origin="https://monitor.example.com",
            analyze_runs_per_hour=0,
        )
