"""Atomic cross-replica TTS capability claims and scoped quota checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, SpeechSynthesisRateLimitError

_SCHEMA = "service_identity"
_TABLE = "speech_synthesis_claim"
_PURGE_BATCH_SIZE = 200

_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))")
_EXISTING_SQL = text(
    f"SELECT 1 FROM {_SCHEMA}.{_TABLE} WHERE capability_digest = :capability_digest"
)
_PURGE_SQL = text(
    f"DELETE FROM {_SCHEMA}.{_TABLE} WHERE capability_digest IN ("
    f" SELECT capability_digest FROM {_SCHEMA}.{_TABLE}"
    " WHERE expires_at < :cutoff ORDER BY expires_at LIMIT :batch_size"
    ")"
)
_USAGE_SQL = text(
    f"SELECT count(*) AS request_count,"
    " COALESCE(sum(character_count), 0) AS character_count"
    f" FROM {_SCHEMA}.{_TABLE}"
    " WHERE claimed_at >= :window_start AND ("
    " (:scope_type = 'client' AND client_ip_hash = :scope_value) OR"
    " (:scope_type = 'actor' AND CAST(actor_id AS text) = :scope_value) OR"
    " (:scope_type = 'tenant' AND CAST(tenant_id AS text) = :scope_value)"
    ")"
)
_CLAIM_SQL = text(
    f"INSERT INTO {_SCHEMA}.{_TABLE} ("
    " capability_digest, tenant_id, actor_id, session_id, agent_run_id,"
    " client_ip_hash, character_count, expires_at"
    ") VALUES ("
    " :capability_digest, :tenant_id, :actor_id, :session_id, :agent_run_id,"
    " :client_ip_hash, :character_count, :expires_at"
    ") ON CONFLICT (capability_digest) DO NOTHING RETURNING capability_digest"
)


@dataclass(frozen=True, slots=True)
class SpeechSynthesisQuota:
    window_seconds: int
    client_requests: int
    client_characters: int
    actor_requests: int
    actor_characters: int
    tenant_requests: int
    tenant_characters: int


class SpeechSynthesisClaimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(
        self,
        *,
        capability_digest: str,
        tenant_id: UUID,
        actor_id: UUID,
        session_id: UUID,
        agent_run_id: UUID,
        client_ip_hash: str,
        character_count: int,
        expires_at: datetime,
        quota: SpeechSynthesisQuota,
        now: datetime | None = None,
    ) -> None:
        claimed_at = (now or datetime.now(UTC)).astimezone(UTC)
        window = timedelta(seconds=quota.window_seconds)
        scopes = (
            ("actor", str(actor_id), quota.actor_requests, quota.actor_characters),
            ("client", client_ip_hash, quota.client_requests, quota.client_characters),
            ("tenant", str(tenant_id), quota.tenant_requests, quota.tenant_characters),
        )

        for scope_type, scope_value, _, _ in sorted(scopes):
            await self._session.execute(
                _LOCK_SQL,
                {"lock_key": f"speech-synthesis:{scope_type}:{scope_value}"},
            )

        if await self._session.scalar(
            _EXISTING_SQL,
            {"capability_digest": capability_digest},
        ):
            raise AuthenticationError("Speech synthesis capability is invalid or unavailable")

        await self._session.execute(
            _PURGE_SQL,
            {
                "cutoff": claimed_at - window,
                "batch_size": _PURGE_BATCH_SIZE,
            },
        )

        for scope_type, scope_value, request_limit, character_limit in scopes:
            row = (
                await self._session.execute(
                    _USAGE_SQL,
                    {
                        "scope_type": scope_type,
                        "scope_value": scope_value,
                        "window_start": claimed_at - window,
                    },
                )
            ).one()
            if (
                int(row.request_count) + 1 > request_limit
                or int(row.character_count) + character_count > character_limit
            ):
                # The first expiring row may not free enough character budget.
                # Return the full bounded window instead of encouraging a retry
                # that can deterministically receive another 429.
                raise SpeechSynthesisRateLimitError(quota.window_seconds)

        claimed = await self._session.scalar(
            _CLAIM_SQL,
            {
                "capability_digest": capability_digest,
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "session_id": session_id,
                "agent_run_id": agent_run_id,
                "client_ip_hash": client_ip_hash,
                "character_count": character_count,
                "expires_at": expires_at,
            },
        )
        if claimed is None:
            raise AuthenticationError("Speech synthesis capability is invalid or unavailable")
