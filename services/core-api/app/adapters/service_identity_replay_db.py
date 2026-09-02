"""Durable, cross-replica replay claims backed by PostgreSQL.

The claim is made with ``INSERT ... ON CONFLICT DO NOTHING`` in its own short
transaction, so it survives even when the request it authenticated later rolls
back.  The table lives outside ``eldercare_ai``: replay claims are operational
security state, not domain state.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

NONCE_SCHEMA = "service_identity"
NONCE_TABLE = "credential_nonce"

#: Expired rows are removed in bounded batches so a claim never turns into an
#: unbounded delete on a table that a burst of traffic has grown.
_PURGE_BATCH_SIZE = 200

_CLAIM_SQL = text(
    f"INSERT INTO {NONCE_SCHEMA}.{NONCE_TABLE} "
    "(audience, credential_id, issuer, subject, expires_at) "
    "VALUES (:audience, :credential_id, :issuer, :subject, :expires_at) "
    "ON CONFLICT (audience, credential_id) DO NOTHING "
    "RETURNING credential_id"
)

_PURGE_SQL = text(
    f"DELETE FROM {NONCE_SCHEMA}.{NONCE_TABLE} "
    "WHERE (audience, credential_id) IN ("
    f"    SELECT audience, credential_id FROM {NONCE_SCHEMA}.{NONCE_TABLE} "
    "     WHERE expires_at < :cutoff ORDER BY expires_at LIMIT :batch_size"
    ")"
)


class DatabaseReplayStore:
    """Atomic cross-replica claim backed by the shared PostgreSQL nonce table.

    The session factory is resolved per call rather than captured at
    construction: the verifier is cached for the process lifetime, while the
    engine is created during startup and replaced by tests.

    The claim deliberately runs on its own connection, so an authenticated
    request briefly holds two: size the pool for that (the defaults, 5 plus 10
    overflow, leave ample headroom).
    """

    durable = True

    def __init__(
        self,
        session_factory_provider: Callable[[], async_sessionmaker[AsyncSession]],
        *,
        purge_batch_size: int = _PURGE_BATCH_SIZE,
    ) -> None:
        self._session_factory_provider = session_factory_provider
        self._purge_batch_size = purge_batch_size

    async def claim(
        self,
        *,
        issuer: str,
        subject: str,
        audience: str,
        credential_id: str,
        expires_at: datetime,
        now: datetime,
    ) -> bool:
        session_factory = self._session_factory_provider()
        async with session_factory() as session, session.begin():
            # Purging first keeps the table bounded without ever freeing a live
            # credential: only rows whose own expiry has already passed are
            # removed, and the verifier rejects those credentials before it
            # reaches this point.
            await session.execute(
                _PURGE_SQL,
                {"cutoff": now, "batch_size": self._purge_batch_size},
            )
            claimed = await session.scalar(
                _CLAIM_SQL,
                {
                    "audience": audience,
                    "credential_id": credential_id,
                    "issuer": issuer,
                    "subject": subject,
                    "expires_at": expires_at,
                },
            )
        return claimed is not None
