"""Integration tests run against a disposable database from scripts/dev_entrypoint.py."""
import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from webmonitor.db import get_engine, get_session_factory
from webmonitor.models import Base


@pytest_asyncio.fixture(autouse=True)
async def isolated_engine():
    """Each test owns its event loop, so the cached engine must not leak across tests."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield
    try:
        await get_engine().dispose()
    except Exception:
        pass
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest_asyncio.fixture
async def session():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as active:
            yield active
    finally:
        await engine.dispose()
