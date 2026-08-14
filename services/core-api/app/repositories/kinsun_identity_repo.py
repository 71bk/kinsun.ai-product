"""Persistence boundary for Kinsun-owned email authentication."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kinsun_identity import KinsunEmailChallenge
from app.models.line_identity import ExternalIdentity


class KinsunIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"kinsun-email:v{key_version}:{subject_digest}"},
        )

    async def get_pending_by_subject(
        self,
        *,
        subject_digest: str,
        key_version: int,
        for_update: bool = False,
    ) -> KinsunEmailChallenge | None:
        statement = select(KinsunEmailChallenge).where(
            KinsunEmailChallenge.external_subject_digest == subject_digest,
            KinsunEmailChallenge.digest_key_version == key_version,
            KinsunEmailChallenge.status == "PENDING",
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_by_token_digest(
        self,
        token_digest: str,
        *,
        for_update: bool = False,
    ) -> KinsunEmailChallenge | None:
        statement = select(KinsunEmailChallenge).where(
            KinsunEmailChallenge.token_digest == token_digest,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def list_identities_by_subject(
        self,
        *,
        subject_digest: str,
        key_version: int,
        for_update: bool = False,
    ) -> list[ExternalIdentity]:
        statement = (
            select(ExternalIdentity)
            .where(
                ExternalIdentity.provider == "KINSUN",
                ExternalIdentity.external_subject_digest == subject_digest,
                ExternalIdentity.digest_key_version == key_version,
            )
            .order_by(ExternalIdentity.created_at, ExternalIdentity.id)
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    def add_challenge(self, challenge: KinsunEmailChallenge) -> None:
        self._session.add(challenge)

    async def flush(self) -> None:
        await self._session.flush()
