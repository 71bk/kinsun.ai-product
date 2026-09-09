"""Committed-data lifecycle for serial tests on a disposable database only."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.base import Base


async def truncate_test_tables(engine: AsyncEngine) -> None:
    """Preserve the existing metadata/existence filter for temporary test tables."""
    async with engine.begin() as conn:
        # Never wait indefinitely on a leaked connection's transaction lock.
        await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        existing = {
            row[0]
            for row in await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'eldercare_ai'"
                )
            )
        }
        tables = [table.fullname for table in Base.metadata.sorted_tables if table.name in existing]
        if tables:
            await conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} CASCADE"))


async def cleanup_committed_session(session: AsyncSession, engine: AsyncEngine) -> None:
    """Release transactions before cleanup, reporting every cleanup failure."""
    errors = []
    for operation in (session.rollback, session.close):
        try:
            await operation()
        except Exception as error:
            errors.append(error)
    if errors:
        try:
            await session.invalidate()
        except Exception as error:
            # Do not attempt TRUNCATE while connection release is unconfirmed.
            raise ExceptionGroup("Test session release failed", [*errors, error]) from None
    try:
        await truncate_test_tables(engine)
    except Exception as error:
        errors.append(error)
    if errors:
        raise ExceptionGroup("Committed test cleanup failed", errors)


@asynccontextmanager
async def committed_session_scope(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Keep body and cleanup on the caller's loop; never suppress body failures."""
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await cleanup_committed_session(session, engine)
