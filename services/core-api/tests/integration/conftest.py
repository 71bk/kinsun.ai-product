"""Integration test configuration — database fixtures and session management.

Provides:
- Session-scoped event loop for async fixtures
- Session-scoped test engine connected to TEST_DATABASE_URL
- Alembic upgrade head run once per test session
- Per-test db_session with transaction rollback isolation
- committed_session for tests needing visible committed data
- AsyncClient with FakeAuthenticator and test engine dependency overrides
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import get_db_engine
from app.main import create_app
from app.middleware.auth import (
    ActorContext,
    FakeAuthenticator,
    get_authenticator,
)

# On Windows, asyncio defaults to ProactorEventLoopPolicy. Combined with
# asyncpg + SQLAlchemy's greenlet-based async bridging across many fixtures
# and Hypothesis-managed per-example event loops (see
# test_property_outbox_atomicity.py / test_property_tenant_scope.py), this
# intermittently raises `RuntimeError: ... Future ... attached to a
# different loop` / `InterfaceError: another operation is in progress` even
# when everything is nominally on "the same" session-scoped loop.
# SelectorEventLoopPolicy doesn't support subprocesses, which none of these
# tests need, and is the standard workaround for this class of asyncio/
# asyncpg flakiness on Windows. Must be set before pytest-asyncio creates
# its first event loop, so this runs at conftest import time.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ─── Test database URL ───────────────────────────────────────────────────────

DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test"
)


def get_test_database_url() -> str:
    """Async (asyncpg) URL for the test database."""
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _sync_url(async_url: str) -> str:
    """Convert an asyncpg URL to the psycopg URL Alembic uses.

    Alembic runs migrations synchronously through psycopg; the application
    runs asynchronously through asyncpg. Same database, two drivers.
    """
    return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg://")


# ─── Session-scoped test engine ──────────────────────────────────────────────
#
# There is deliberately no custom `event_loop` fixture. pytest-asyncio 0.24
# deprecated overriding it, and a session-scoped override left this
# session-scoped engine bound to a different loop than the tests ran in —
# every asyncpg call then failed with "attached to a different loop".
# The loop scope now comes from asyncio_default_fixture_loop_scope in
# pyproject.toml instead.


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create an async engine connected to the test database.

    Uses NullPool: every checkout opens a genuinely fresh asyncpg connection
    and every checkin closes it, rather than reusing one from a pool. The
    app's `RequestLoggerMiddleware` is a Starlette `BaseHTTPMiddleware`,
    which runs the actual endpoint in a separate anyio task from the
    outer request task; a pooled asyncpg connection checked out across that
    boundary intermittently raises `RuntimeError: Future ... attached to a
    different loop` / `InterfaceError: another operation is in progress`
    even though everything runs on the same session-scoped event loop. Since
    app/middleware/logging.py cannot be edited from tests/, NullPool avoids
    the failure class entirely by never handing out a connection that was
    established under a different task context.
    """
    engine = create_async_engine(get_test_database_url(), echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


# ─── Run Alembic migrations once per session ─────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Apply `alembic upgrade head` once per test session.

    Runs synchronously before any async fixture starts, so the schema exists
    regardless of event loop setup. alembic/env.py reads DATABASE_URL from the
    environment, so the sync test URL is injected for the duration of the call.

    Nothing is dropped at teardown: the eldercare_ai schema is owned by the
    baseline migration, not by the test session, and each test already rolls
    its own transaction back.
    """
    from alembic import command
    from alembic.config import Config

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    alembic_cfg = Config(os.path.join(project_root, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(project_root, "alembic"))

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = _sync_url(get_test_database_url())
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

    yield


def _run_alembic_upgrade(connection, alembic_cfg):
    """Run Alembic upgrade head using the provided synchronous connection.

    Passes the connection via config.attributes so that env.py uses it
    directly instead of creating its own engine.
    """
    from alembic import command

    alembic_cfg.attributes["connection"] = connection
    command.upgrade(alembic_cfg, "head")


# ─── Per-test db_session with transaction rollback ───────────────────────────


@pytest_asyncio.fixture(loop_scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Per-test async session wrapped in a transaction that is rolled back.

    Ensures complete test isolation — no data persists between tests.

    Deliberately does NOT depend on the session-scoped `test_engine` fixture.
    `db_session` yields its live connection straight to the test body (unlike
    `committed_session`, which the test body never touches directly — see its
    docstring), so setup and the test's own repository calls must run in the
    same task context. When this used the shared session-scoped engine,
    running the full integration suite (as opposed to this file alone) could
    raise `RuntimeError: ... attached to a different loop`. This fixture uses
    an explicit function-scoped loop because its live session is consumed by
    the function-scoped test body. A dedicated engine created and disposed
    within the same fixture keeps setup, repository calls, and teardown on
    that one loop.
    """
    engine = create_async_engine(get_test_database_url(), echo=False, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield session
            finally:
                await session.close()
                await transaction.rollback()
    finally:
        await engine.dispose()


# ─── committed_session for tests needing visible committed data ──────────────


@pytest_asyncio.fixture
async def committed_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Session that commits data — for tests needing cross-connection visibility.

    Performs explicit cleanup by truncating all user tables after the test.
    """
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        # Cleanup: truncate all tables that are part of our metadata AND
        # actually exist right now.
        #
        # Every table lives in the `eldercare_ai` schema (see app/db/base.py's
        # Base.metadata = MetaData(schema=SCHEMA_NAME)), which is NOT on the
        # default connection search_path (just "$user", public) — table.name
        # alone ("outbox_event") does not resolve. table.fullname includes
        # the schema qualifier ("eldercare_ai.outbox_event").
        #
        # The existence check matters because Base.metadata is process-wide:
        # test_property_outbox_atomicity.py / test_property_tenant_scope.py
        # define their own throwaway entities as subclasses of BaseModel,
        # which registers their tables on this SAME Base.metadata as soon as
        # those modules are merely *imported* (pytest collects every test
        # file up front) — regardless of whether their own module-scoped
        # fixture has created (or has already dropped) those tables yet. An
        # unconditional TRUNCATE would fail with UndefinedTableError whenever
        # this fixture's cleanup runs before/after that table's brief
        # lifetime.
        async with test_engine.begin() as conn:
            existing = {
                row[0]
                for row in await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'eldercare_ai'"
                    )
                )
            }
            tables_to_truncate = [
                table.fullname for table in Base.metadata.sorted_tables if table.name in existing
            ]
            if tables_to_truncate:
                await conn.execute(
                    text("TRUNCATE TABLE " f"{', '.join(tables_to_truncate)} CASCADE")
                )


# ─── Test actor context ──────────────────────────────────────────────────────


@pytest.fixture
def test_actor_id() -> uuid.UUID:
    """Fixed actor ID for test reproducibility."""
    return uuid.UUID("00000000-0000-4000-a000-000000000001")


@pytest.fixture
def test_tenant_id() -> uuid.UUID:
    """Fixed tenant ID for test reproducibility."""
    return uuid.UUID("00000000-0000-4000-a000-000000000002")


@pytest.fixture
def test_actor_context(test_actor_id, test_tenant_id) -> ActorContext:
    """Pre-built ActorContext for tests."""
    return ActorContext(
        actor_id=test_actor_id,
        actor_role="care_worker",
        tenant_id=test_tenant_id,
    )


# ─── AsyncClient with dependency overrides ───────────────────────────────────


@pytest_asyncio.fixture
async def client(test_engine, test_actor_id, test_tenant_id) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with FakeAuthenticator and test engine dependency overrides.

    The app's get_authenticator dependency is overridden to return a
    FakeAuthenticator with known test values. The get_db_engine dependency
    is overridden to provide a test DatabaseEngine wrapper.
    """
    app = create_app()

    # Create a FakeAuthenticator with fixed test identity
    fake_auth = FakeAuthenticator(
        actor_id=test_actor_id,
        actor_role="care_worker",
        tenant_id=test_tenant_id,
    )

    # Create a minimal DatabaseEngine-like object backed by test_engine
    test_db_engine = _TestDatabaseEngine(test_engine)

    # Override dependencies
    app.dependency_overrides[get_authenticator] = lambda: fake_auth
    app.dependency_overrides[get_db_engine] = lambda: test_db_engine

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class _TestDatabaseEngine:
    """Minimal wrapper around a test engine to satisfy DatabaseEngine interface.

    Provides the same properties that app code uses (engine, session_factory,
    is_ready) without going through the full DatabaseEngine constructor.
    """

    def __init__(self, engine):
        self._engine = engine
        self._session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    @property
    def engine(self):
        return self._engine

    @property
    def session_factory(self):
        return self._session_factory

    @property
    def is_ready(self) -> bool:
        return True

    async def check_connectivity(self) -> bool:
        return True
