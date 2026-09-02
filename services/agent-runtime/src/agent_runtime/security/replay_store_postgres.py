"""Durable, cross-replica replay claims backed by PostgreSQL.

The claim targets the shared ``service_identity.credential_nonce`` table owned
by the Core migrations.  The Runtime never reads or writes a domain table: this
schema holds operational security state only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from agent_runtime.security.replay_store import ReplayStoreError

NONCE_SCHEMA = "service_identity"
NONCE_TABLE = "credential_nonce"

#: Expired rows are removed in bounded batches so a claim never becomes an
#: unbounded delete on a table a traffic burst has grown.
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


class PostgresReplayStore:
    """Atomic cross-replica claim against the shared nonce table."""

    durable = True

    def __init__(self, engine: AsyncEngine, *, purge_batch_size: int = _PURGE_BATCH_SIZE) -> None:
        self._engine = engine
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
        try:
            async with self._engine.begin() as connection:
                # Purging first bounds the table without freeing a live claim:
                # only already-expired rows are removed, and those credentials
                # are rejected by the TTL check before reaching this point.
                await connection.execute(
                    _PURGE_SQL,
                    {"cutoff": now, "batch_size": self._purge_batch_size},
                )
                claimed = await connection.scalar(
                    _CLAIM_SQL,
                    {
                        "audience": audience,
                        "credential_id": credential_id,
                        "issuer": issuer,
                        "subject": subject,
                        "expires_at": expires_at,
                    },
                )
        except Exception as exc:
            # Driver messages can carry endpoints or credentials. Fail closed
            # with the exception type only; the caller converts this to the same
            # fixed authentication failure as any other rejection.
            raise ReplayStoreError(f"replay claim failed: {type(exc).__name__}") from exc
        return claimed is not None

    async def aclose(self) -> None:
        await self._engine.dispose()


def build_replay_engine(database_url: str, *, statement_timeout_ms: int = 5_000) -> AsyncEngine:
    """Create a small pool for nonce claims without connecting at import time."""

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        database_url,
        pool_size=1,
        max_overflow=2,
        pool_pre_ping=True,
        pool_timeout=max(1.0, statement_timeout_ms / 1000),
        connect_args={
            "server_settings": {
                "application_name": "kinsun-agent-runtime-service-identity",
                "statement_timeout": str(statement_timeout_ms),
            }
        },
    )
