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
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.session import get_db_engine
from app.main import create_app
from app.middleware.auth import (
    ActorContext,
    FakeAuthenticator,
    get_authenticator,
)
from tests.committed_session import committed_session_scope

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

    NullPool prevents idle connections from being reused across test loops.
    It does not make a checked-out connection or live AsyncSession safe to
    move between loops. Fixtures sharing sessions with test bodies therefore
    use explicit function loops, including their dependent seed fixtures.
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
    Both `db_session` and `committed_session` yield live sessions to test
    bodies, so setup, repository calls, and teardown must run on the same
    event loop. When this used the shared session-scoped engine,
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


@pytest_asyncio.fixture(loop_scope="function")
async def committed_session() -> AsyncGenerator[AsyncSession, None]:
    """Function-loop session, also consumed by function-loop seed fixtures.

    A dedicated NullPool engine is created and disposed on that same loop.
    Committed rows are visible to request connections; cleanup always ends
    the session transaction before truncating the disposable test tables.
    """
    engine = create_async_engine(
        get_test_database_url(), echo=False, hide_parameters=True, poolclass=NullPool
    )
    try:
        async with committed_session_scope(engine) as session:
            yield session
    finally:
        await engine.dispose()


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
