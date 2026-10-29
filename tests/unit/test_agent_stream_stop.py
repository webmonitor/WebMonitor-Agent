"""A cancelled agent run must reach its terminal state even if the stream stalls."""
import asyncio

import pytest

from webmonitor.agent import orchestration


class StalledStream:
    """A stream that ignores cancellation and never ends on its own."""

    def __init__(self) -> None:
        self.cancelled: str | None = None

    def cancel(self, *, mode: str) -> None:
        self.cancelled = mode

    async def stream_events(self):
        while True:
            await asyncio.sleep(60)
            yield None


class EndedStream:
    def __init__(self) -> None:
        self.cancelled: str | None = None

    def cancel(self, *, mode: str) -> None:
        self.cancelled = mode

    async def stream_events(self):
        return
        yield None


@pytest.mark.asyncio
async def test_stopping_a_stalled_stream_returns(monkeypatch):
    monkeypatch.setattr(orchestration, "STOP_STREAM_SECONDS", 0.05)
    stream = StalledStream()
    async with asyncio.timeout(2):
        await orchestration._stop_stream(stream)
    assert stream.cancelled == "immediate"


@pytest.mark.asyncio
async def test_stopping_an_ended_stream_drains_it():
    stream = EndedStream()
    await orchestration._stop_stream(stream)
    assert stream.cancelled == "immediate"


@pytest.mark.asyncio
async def test_stopping_without_a_stream_is_a_no_op():
    await orchestration._stop_stream(None)
