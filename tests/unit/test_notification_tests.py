"""Explicit notification tests reuse transports without production records."""
import json
from uuid import uuid4

import pytest

from webmonitor.errors import DomainError
from webmonitor.notifications.errors import DeliveryFailure
from webmonitor.security.auth import CurrentUser
from webmonitor.services import notifications


ADMIN = CurrentUser(uuid4(), role="admin")


@pytest.mark.asyncio
async def test_test_email_uses_the_smtp_transport(monkeypatch):
    captured = {}

    async def accepted(delivery, rendered):
        captured["delivery"] = delivery
        captured["rendered"] = rendered
        return 250

    monkeypatch.setattr(notifications, "send_email", accepted)
    result = await notifications.send_test_email(ADMIN, "ops@example.com")

    assert result.model_dump(mode="json") == {"channel": "email", "response_code": 250}
    assert captured["delivery"].recipient == "ops@example.com"
    assert captured["delivery"].message_id.startswith("<")
    assert "test email" in captured["rendered"]["text"]
    assert "monitoring event was created" in captured["rendered"]["text"]


@pytest.mark.asyncio
async def test_test_webhook_validates_and_uses_the_json_transport(monkeypatch):
    captured = {}

    async def accepted(delivery):
        captured["delivery"] = delivery
        return 204

    monkeypatch.setattr(notifications, "send_webhook", accepted)
    result = await notifications.send_test_webhook(ADMIN, "https://hooks.example.com/ops")

    assert result.model_dump(mode="json") == {"channel": "webhook", "response_code": 204}
    delivery = captured["delivery"]
    assert delivery.recipient == "https://hooks.example.com/ops"
    assert json.loads(delivery.body_text) == delivery.payload
    assert delivery.payload["test"] is True
    assert "event" not in delivery.payload and "monitor" not in delivery.payload


@pytest.mark.asyncio
async def test_test_webhook_rejects_an_invalid_target_before_sending(monkeypatch):
    called = False

    async def send(delivery):
        nonlocal called
        called = True
        return 200

    monkeypatch.setattr(notifications, "send_webhook", send)
    with pytest.raises(DomainError) as raised:
        await notifications.send_test_webhook(ADMIN, "not a webhook URL")
    assert raised.value.code == "url_forbidden"
    assert raised.value.status == 422
    assert called is False


@pytest.mark.asyncio
async def test_test_email_surfaces_sanitized_transport_failure(monkeypatch):
    async def refused(delivery, rendered):
        raise DeliveryFailure("smtp_recipient_refused", "SMTP server refused the recipient")

    monkeypatch.setattr(notifications, "send_email", refused)
    with pytest.raises(DomainError) as raised:
        await notifications.send_test_email(ADMIN, "ops@example.com")
    assert raised.value.code == "smtp_recipient_refused"
    assert raised.value.status == 502
    assert raised.value.message == "SMTP server refused the recipient"


@pytest.mark.asyncio
async def test_test_webhook_surfaces_transport_failure(monkeypatch):
    async def rejected(delivery):
        raise DeliveryFailure("webhook_rejected", "Webhook endpoint rejected the request", False, 400)

    monkeypatch.setattr(notifications, "send_webhook", rejected)
    with pytest.raises(DomainError) as raised:
        await notifications.send_test_webhook(ADMIN, "https://hooks.example.com/ops")
    assert raised.value.code == "webhook_rejected"
    assert raised.value.status == 502
    assert raised.value.message == "Webhook endpoint rejected the request"


@pytest.mark.asyncio
async def test_notification_tests_are_admin_only(monkeypatch):
    called = False

    async def send(*args):
        nonlocal called
        called = True
        return 200

    monkeypatch.setattr(notifications, "send_email", send)
    monkeypatch.setattr(notifications, "send_webhook", send)
    member = CurrentUser(uuid4(), role="member")
    for operation in (
        notifications.send_test_email(member, "ops@example.com"),
        notifications.send_test_webhook(member, "https://hooks.example.com/ops"),
    ):
        with pytest.raises(DomainError) as raised:
            await operation
        assert raised.value.code == "forbidden"
    assert called is False
