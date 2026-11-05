"""Bounded JSON POST delivery through the mandatory ACL egress proxy.

The stored `body_text` is the exact payload that was rendered and confirmed, so a
delivery never re-renders after the monitor changes. Redirects are not followed:
the destination was validated once, and following a redirect would bypass that.
"""
import asyncio

import httpx

from webmonitor.config import get_settings
from webmonitor.errors import DomainError
from webmonitor.notifications.errors import DeliveryFailure
from webmonitor.security.egress import validate_webhook_url

RETRYABLE_STATUS = frozenset({408, 425, 429})


def _status_failure(status: int) -> DeliveryFailure:
    retryable = status in RETRYABLE_STATUS or status >= 500
    return DeliveryFailure("webhook_rejected", "Webhook endpoint rejected the request",
                           retryable, status)


async def send_webhook(delivery, *,
                       transport: httpx.AsyncBaseTransport | None = None) -> int:
    try:
        url = validate_webhook_url(delivery.recipient)
    except DomainError:
        raise DeliveryFailure("webhook_url_forbidden", "Webhook URL is not permitted") from None
    event = (delivery.payload or {}).get("event") or {}
    monitor = (delivery.payload or {}).get("monitor") or {}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "WebMonitor-Agent",
        "X-WebMonitor-Event": str(event.get("type") or ""),
        "X-WebMonitor-Monitor": str(monitor.get("id") or ""),
        "X-WebMonitor-Delivery": str(delivery.id),
    }
    try:
        async with asyncio.timeout(20), httpx.AsyncClient(
            proxy=None if transport else get_settings().egress_proxy_url,
            transport=transport, trust_env=False, follow_redirects=False,
            timeout=15,
        ) as client, client.stream(
            "POST", url, content=delivery.body_text.encode("utf-8"), headers=headers,
        ) as response:
            # The status is the whole result; the response body is never stored.
            if 200 <= response.status_code < 300:
                return response.status_code
            raise _status_failure(response.status_code)
    except DeliveryFailure:
        raise
    except (TimeoutError, httpx.TimeoutException):
        raise DeliveryFailure("webhook_timeout", "Webhook request timed out", True) from None
    except httpx.ProxyError as exc:
        if str(exc).startswith("403"):
            raise DeliveryFailure("webhook_forbidden",
                                  "Webhook destination is not permitted") from None
        raise DeliveryFailure("webhook_unavailable", "Webhook proxy connection failed",
                              True) from None
    except httpx.HTTPError:
        raise DeliveryFailure("webhook_unavailable", "Webhook connection failed", True) from None
