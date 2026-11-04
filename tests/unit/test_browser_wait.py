"""Browser navigation stays bounded when a page never reaches network idle."""

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from webmonitor.collection.browser import (
    NAVIGATION_TIMEOUT_MS,
    SETTLE_TIMEOUT_MS,
    _navigate,
    _settle,
)
from webmonitor.errors import DomainError


@pytest.mark.asyncio
async def test_navigation_uses_domcontentloaded_and_maps_timeout():
    calls = []

    class Page:
        async def goto(self, target, *, wait_until, timeout):
            calls.append((target, wait_until, timeout))
            raise PlaywrightTimeoutError("slow document")

    with pytest.raises(DomainError) as error:
        await _navigate(Page(), "https://example.com/")
    assert error.value.code == "collection_timeout"
    assert calls == [("https://example.com/", "domcontentloaded", NAVIGATION_TIMEOUT_MS)]


@pytest.mark.asyncio
async def test_settle_ignores_a_busy_network():
    calls = []

    class Page:
        async def wait_for_load_state(self, state, *, timeout):
            calls.append((state, timeout))
            raise PlaywrightTimeoutError("still polling")

    await _settle(Page())
    assert calls == [("networkidle", SETTLE_TIMEOUT_MS)]


@pytest.mark.asyncio
async def test_settle_does_not_hide_a_broken_page():
    class Page:
        async def wait_for_load_state(self, state, *, timeout):
            raise PlaywrightError("page closed")

    with pytest.raises(PlaywrightError):
        await _settle(Page())
