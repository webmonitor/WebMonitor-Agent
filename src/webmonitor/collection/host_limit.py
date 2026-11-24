"""Process-local per-origin concurrency, shared by HTTP and browser collection."""
import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from webmonitor.config import get_settings

_locks: OrderedDict[str, asyncio.Semaphore] = OrderedDict()
_fallback: asyncio.Semaphore | None = None
_MAX_ORIGINS = 1024


def _slot(origin: str) -> asyncio.Semaphore:
    global _fallback
    limit = get_settings().target_domain_concurrency
    semaphore = _locks.get(origin)
    if semaphore is not None:
        _locks.move_to_end(origin)
        return semaphore
    if len(_locks) < _MAX_ORIGINS:
        semaphore = asyncio.Semaphore(limit)
        _locks[origin] = semaphore
        return semaphore
    # An unexpectedly large target set cannot grow process memory without bound.
    if _fallback is None:
        _fallback = asyncio.Semaphore(limit)
    return _fallback


@asynccontextmanager
async def host_slot(url: str):
    origin = (urlsplit(url).hostname or "").casefold()
    semaphore = _slot(origin)
    async with semaphore:
        yield
