"""Reused Chromium processes rotate only after their isolated leases drain."""
import asyncio

import pytest
import pytest_asyncio

from webmonitor.collection import browser as browser_module
from webmonitor.collection.browser import (
    _browser_process,
    _lease_process,
    _release_process,
    shutdown_browser,
)
from webmonitor.config import get_settings


class FakeContext:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.connected = True
        self.closed = False
        self.contexts = []

    def is_connected(self):
        return self.connected

    async def new_context(self, **kwargs):
        context = FakeContext()
        self.contexts.append((context, kwargs))
        return context

    async def close(self):
        self.closed = True
        self.connected = False


class FakePlaywright:
    def __init__(self, driver):
        self.driver = driver
        self.chromium = driver

    async def stop(self):
        self.driver.stops += 1


class FakeDriver:
    def __init__(self):
        self.browsers = []
        self.stops = 0

    async def start(self):
        return FakePlaywright(self)

    async def launch(self, **kwargs):
        browser = FakeBrowser()
        self.browsers.append(browser)
        return browser


@pytest_asyncio.fixture(autouse=True)
async def clean_process(monkeypatch):
    browser_module._process = None
    browser_module._process_condition = None
    monkeypatch.setenv("BROWSER_REUSE_REQUESTS", "2")
    monkeypatch.setenv("BROWSER_REUSE_SECONDS", "300")
    get_settings.cache_clear()
    yield
    await shutdown_browser()
    get_settings.cache_clear()


def fake_playwright(monkeypatch) -> FakeDriver:
    driver = FakeDriver()
    monkeypatch.setattr(browser_module, "async_playwright", lambda: driver)
    return driver


@pytest.mark.asyncio
async def test_two_collections_share_one_process_with_fresh_contexts(monkeypatch):
    driver = fake_playwright(monkeypatch)
    async with _browser_process() as first:
        await first.new_context()
    async with _browser_process() as second:
        await second.new_context()
    assert first is second
    assert len(driver.browsers) == 1
    assert len(first.contexts) == 2

    async with _browser_process():
        pass
    assert len(driver.browsers) == 2
    assert first.closed is True


@pytest.mark.asyncio
async def test_expired_process_waits_for_active_leases_before_rotation(monkeypatch):
    driver = fake_playwright(monkeypatch)
    first = await _lease_process()
    second = await _lease_process()
    waiting = asyncio.create_task(_lease_process())
    await asyncio.sleep(0)
    assert not waiting.done()
    assert driver.browsers[0].closed is False

    await _release_process(first)
    await asyncio.sleep(0)
    assert not waiting.done()
    await _release_process(second)
    third = await asyncio.wait_for(waiting, timeout=1)
    assert third is not first
    assert driver.browsers[0].closed is True
    await _release_process(third)


@pytest.mark.asyncio
async def test_ttl_and_disconnection_rotate_the_process(monkeypatch):
    driver = fake_playwright(monkeypatch)
    now = [100.0]
    monkeypatch.setattr(browser_module, "monotonic", lambda: now[0])
    async with _browser_process() as first:
        pass
    now[0] += 301
    async with _browser_process() as second:
        pass
    assert second is not first

    second.connected = False
    async with _browser_process() as third:
        pass
    assert third is not second
    assert len(driver.browsers) == 3


@pytest.mark.asyncio
async def test_shutdown_closes_browser_and_playwright(monkeypatch):
    driver = fake_playwright(monkeypatch)
    async with _browser_process() as browser:
        pass
    await shutdown_browser()
    assert browser.closed is True
    assert driver.stops == 1
    assert browser_module._process is None
