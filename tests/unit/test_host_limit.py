"""Per-origin collection limits and deterministic schedule jitter."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from webmonitor.collection import host_limit
from webmonitor.collection.fetch import fetch_bounded
from webmonitor.config import get_settings
from webmonitor.services.runs import _schedule_jitter


@pytest.mark.asyncio
async def test_http_requests_are_bounded_per_origin(monkeypatch):
    monkeypatch.setenv("TARGET_DOMAIN_CONCURRENCY", "1")
    get_settings.cache_clear()
    host_limit._locks.clear()
    active = 0
    maximum = 0

    async def handler(request):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.02)
        active -= 1
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"))

    transport = httpx.MockTransport(handler)
    await asyncio.gather(*[fetch_bounded("https://example.com/", accept="text/plain",
        max_bytes=100, transport=transport) for _ in range(4)])
    assert maximum == 1
    host_limit._locks.clear()
    get_settings.cache_clear()


def test_schedule_jitter_is_stable_and_bounded():
    monitor = SimpleNamespace(id=uuid4(), spec_version=3, interval_seconds=60)
    first = _schedule_jitter(monitor)
    assert first == _schedule_jitter(monitor)
    assert 0 <= first <= 6
    monitor.interval_seconds = 86400
    assert 0 <= _schedule_jitter(monitor) <= 60
