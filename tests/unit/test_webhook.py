"""The webhook channel sends the frozen JSON body through the destination policy."""
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.notifications.errors import DeliveryFailure
from webmonitor.notifications.webhook import send_webhook
from webmonitor.security.egress import validate_webhook_url


class FakeDelivery:
    def __init__(self, url="https://hooks.example.com/ops"):
        self.id = uuid4()
        self.recipient = url
        self.payload = {"event": {"type": "content_changed"},
                        "monitor": {"id": "monitor-1"}}
        self.body_text = json.dumps({"event": {"type": "content_changed"},
                                     "fields": {"title": "Open"}})


def production_settings(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    monkeypatch.setenv("DEVELOPMENT_MODE", "false")
    monkeypatch.setenv("APP_ORIGIN", "https://monitor.example.com")
    get_settings.cache_clear()


def test_webhooks_require_https_and_a_public_destination(monkeypatch):
    production_settings(monkeypatch)
    assert validate_webhook_url("https://hooks.example.com/ops") == \
        "https://hooks.example.com/ops"
    for url, code in (("http://hooks.example.com/ops", "webhook_url_insecure"),
                      ("http://127.0.0.1:9000/hook", "url_forbidden"),
                      ("http://postgres:5432/hook", "url_forbidden"),
                      (None, "webhook_url_missing")):
        with pytest.raises(DomainError) as raised:
            validate_webhook_url(url)
        assert raised.value.code == code


@pytest.mark.asyncio
async def test_send_webhook_posts_the_stored_body_without_following_redirects():
    captured: dict[str, httpx.Headers] = {}
    body: dict[str, Any] = {}
    url: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body["method"] = request.method
        url["value"] = str(request.url)
        body["content"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(202)

    delivery = FakeDelivery()
    assert await send_webhook(delivery, transport=httpx.MockTransport(handler)) == 202
    assert body["method"] == "POST"
    assert url["value"] == "https://hooks.example.com/ops"
    assert body["content"] == delivery.body_text.encode("utf-8")
    headers = captured["headers"]
    assert headers["content-type"] == "application/json"
    assert headers["x-webmonitor-event"] == "content_changed"
    assert headers["x-webmonitor-monitor"] == "monitor-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,retryable", [(400, False), (404, False),
                                              (429, True), (500, True), (302, False)])
async def test_webhook_status_decides_retryability(status, retryable):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="endpoint says no")

    with pytest.raises(DeliveryFailure) as raised:
        await send_webhook(FakeDelivery(), transport=httpx.MockTransport(handler))
    assert raised.value.code == "webhook_rejected"
    assert raised.value.retryable is retryable
    assert raised.value.response_code == status


@pytest.mark.asyncio
async def test_network_failure_is_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(DeliveryFailure) as raised:
        await send_webhook(FakeDelivery(), transport=httpx.MockTransport(handler))
    assert raised.value.code == "webhook_unavailable"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_a_forbidden_destination_is_never_contacted(monkeypatch):
    production_settings(monkeypatch)
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    with pytest.raises(DeliveryFailure) as raised:
        await send_webhook(FakeDelivery("http://127.0.0.1/hook"),
                           transport=httpx.MockTransport(handler))
    assert raised.value.code == "webhook_url_forbidden"
    assert called is False
