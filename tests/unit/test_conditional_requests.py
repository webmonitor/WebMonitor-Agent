"""ETag negotiation avoids bodies without weakening baseline semantics."""
import httpx
import pytest

from webmonitor.collection.api import collect_api
from webmonitor.collection.fetch import FetchResult
from webmonitor.collection.http import collect_http
from webmonitor.schemas.monitors import MonitorSpec


@pytest.mark.asyncio
async def test_html_etag_is_sent_and_304_does_not_extract(monkeypatch):
    calls = []

    async def fake_fetch(url, **kwargs):
        calls.append(kwargs)
        if kwargs.get("headers", {}).get("If-None-Match") == '"v1"':
            return FetchResult(url, 304, httpx.Headers(), b"")
        return FetchResult(url, 200, httpx.Headers({"etag": '"v1"',
            "content-type": "text/html"}), b"<h1>Open</h1>")

    monkeypatch.setattr("webmonitor.collection.http.fetch_bounded", fake_fetch)
    first = await collect_http("https://example.com/")
    assert first.validator == {"etag": '"v1"'}
    second = await collect_http("https://example.com/", validator=first.validator)
    assert second.not_modified is True
    assert second.body is None
    assert second.validator == {"etag": '"v1"'}
    assert calls[1]["headers"] == {"If-None-Match": '"v1"'}


def api_spec(url: str) -> MonitorSpec:
    return MonitorSpec.model_validate({
        "name": "API watch", "url": url, "collection_mode": "http",
        "fields": [{"name": "title", "type": "text", "semantic": "Title", "path": "title"}],
        "change_rules": {"mode": "any", "rules": [{"type": "text_changed", "field": "title"}]},
        "coverage": {"scope": "full", "description": "API response"},
        "source": {"kind": "json", "steps": [{"id": "data", "request": {"url": url}}]},
    })


@pytest.mark.asyncio
async def test_single_step_json_api_uses_etag_and_304():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("if-none-match") == '"api-v1"':
            return httpx.Response(304, stream=httpx.ByteStream(b""))
        return httpx.Response(200, stream=httpx.ByteStream(b'{"title":"Open"}'),
            headers={"etag": '"api-v1"', "content-type": "application/json"})

    spec = api_spec("https://example.com/api")
    transport = httpx.MockTransport(handler)
    first = await collect_api(spec.url, spec, transport=transport)
    assert first.fields["title"] == "Open"
    assert first.validator == {"etag": '"api-v1"'}
    second = await collect_api(spec.url, spec, transport=transport, validator=first.validator)
    assert second.not_modified is True
    assert second.body is None
    assert calls[1].headers["if-none-match"] == '"api-v1"'
