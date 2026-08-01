"""Async SQLAlchemy engine and session factory management.

Manages the database engine lifecycle including connection pooling,
connectivity checks, and graceful shutdown with timeout.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import AppEnv, Settings

logger = logging.getLogger(__name__)


class DatabaseEngine:
    """Manages async SQLAlchemy engine lifecycle.

    Provides connection pooling, connectivity verification, degraded mode
    tracking, and graceful disposal with a configurable timeout.
    """

    def __init__(self, settings: Settings) -> None:
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            echo=settings.app_env == AppEnv.DEVELOPMENT,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._ready: bool = False

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying async engine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the session factory for creating request-scoped sessions."""
        return self._session_factory

    @property
    def is_ready(self) -> bool:
        """Return True if the last connectivity check succeeded."""
        return self._ready

    async def check_connectivity(self) -> bool:
        """Execute SELECT 1 to verify database connectivity.

        Updates the internal readiness state based on the result.
        Returns True if connectivity is confirmed, False otherwise.
        """
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            self._ready = True
            return True
        except Exception:
            logger.warning("Database connectivity check failed", exc_info=True)
            self._ready = False
            return False

    async def dispose(self, timeout: float = 30.0) -> None:
        """Close all connections and dispose of the engine pool.

        Args:
            timeout: Maximum seconds to wait for disposal. Defaults to 30.
        """
        try:
            await asyncio.wait_for(self._engine.dispose(), timeout=timeout)
            self._ready = False
            logger.info("Database engine disposed successfully")
        except TimeoutError:
            logger.error("Database engine disposal timed out after %.1f seconds", timeout)
            self._ready = False
        except Exception:
            logger.error("Error during database engine disposal", exc_info=True)
            self._ready = False
