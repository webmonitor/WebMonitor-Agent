"""Process-local async engine, schema creation and readiness."""
import logging
from functools import lru_cache

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from webmonitor.config import get_settings
from webmonitor.models import Base, User, utc_now

logger = logging.getLogger(__name__)

EXPECTED_TABLES = frozenset({
    "users", "sessions", "invitations", "conversations", "messages", "jobs", "drafts",
    "monitors", "snapshots", "events", "notification_groups", "email_deliveries",
})


@lru_cache
def get_engine():
    return create_async_engine(get_settings().database_url, pool_pre_ping=True,
                               pool_size=5, max_overflow=5)


@lru_cache
def get_session_factory():
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def session_dependency():
    async with get_session_factory()() as session:
        yield session


async def initialize_database() -> None:
    """Create the schema and the first administrator; no migration path exists."""
    settings = get_settings()
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.execute(text("SELECT pg_advisory_xact_lock(774431082)"))
        await connection.run_sync(Base.metadata.create_all)
    admin_email = settings.admin_email.strip()
    if admin_email and settings.admin_password.get_secret_value():
        from webmonitor.services import accounts
        async with get_session_factory()() as session:
            if await session.scalar(select(User.id).limit(1)) is None:
                await accounts.create_user(session, email=admin_email,
                    password=settings.admin_password.get_secret_value(),
                    display_name=admin_email, role="admin")
                await session.commit()
    from webmonitor.storage.evidence import initialize_bucket
    try:
        await initialize_bucket()
    except Exception:
        # Evidence storage is retried by each upload; it must not block startup or
        # readiness, which is a database-only contract.
        logger.warning("Evidence bucket is not available yet")


async def database_ready() -> bool:
    """Database-only contract: reachable and every expected table present."""
    try:
        async with get_session_factory()() as session:
            rows = await session.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"))
            return EXPECTED_TABLES <= {row[0] for row in rows}
    except Exception:
        return False


__all__ = ["EXPECTED_TABLES", "database_ready", "get_engine", "get_session_factory",
           "initialize_database", "session_dependency", "utc_now"]
