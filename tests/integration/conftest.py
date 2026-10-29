"""Integration tests run against a disposable database they create themselves.

`TEST_DATABASE_URL` wins when set. Otherwise the session creates `wm_test_<hex>` on
the PostgreSQL reachable from `PG*`/`POSTGRES_PASSWORD`, and drops only that database
at the end. No shared database is ever migrated, truncated or dropped.
"""
import asyncio
import os
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from webmonitor.config import get_settings
from webmonitor.db import get_engine, get_session_factory
from webmonitor.models import Base

_STATE: dict[str, str] = {}


def _connection() -> dict:
    return {
        "host": os.environ.get("PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("PGPORT", "5432")),
        "user": os.environ.get("PGUSER", "webmonitor"),
        "password": os.environ.get("PGPASSWORD") or os.environ.get("POSTGRES_PASSWORD", ""),
    }


async def _create() -> None:
    settings = _connection()
    admin = await asyncpg.connect(database="postgres", timeout=10, **settings)
    name = "wm_test_" + uuid4().hex
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        _STATE["name"] = name
        _STATE["url"] = URL.create("postgresql+asyncpg", username=settings["user"],
            password=settings["password"], host=settings["host"], port=settings["port"],
            database=name).render_as_string(hide_password=False)
        # Application-level helpers (job wait, agent history, tool steps) open their
        # own sessions through the cached factory, so they must see this database too.
        os.environ["PGDATABASE"] = name
    finally:
        await admin.close()


async def _drop() -> None:
    name = _STATE.get("name")
    if not name:
        return
    admin = await asyncpg.connect(database="postgres", timeout=10, **_connection())
    try:
        await admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                            "WHERE datname = $1 AND pid <> pg_backend_pid()", name)
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await admin.close()


def pytest_sessionstart(session):
    if os.environ.get("TEST_DATABASE_URL"):
        _STATE["url"] = os.environ["TEST_DATABASE_URL"]
        return
    try:
        asyncio.run(_create())
    except Exception:
        # No reachable server: every integration test skips instead of failing.
        _STATE.clear()
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("TEST_DATABASE_URL"):
        return
    if _STATE.get("name"):
        try:
            asyncio.run(_drop())
        except Exception:
            pass


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _STATE.get("url")
    if not url:
        pytest.skip("no TEST_DATABASE_URL and no PostgreSQL for a disposable database")
    return url


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
async def session(database_url):
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as active:
            yield active
    finally:
        await engine.dispose()
