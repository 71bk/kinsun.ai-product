"""Persistence boundary for Google sign-in handoff resolution."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.line_identity import ExternalIdentity
from app.models.pending_identity import PendingExternalIdentity


class GoogleIdentityRepository:
    """Serialize subject handoffs and store only keyed/token digests."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        lock_key = f"google-subject:v{key_version}:{subject_digest}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )

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
                ExternalIdentity.provider == "GOOGLE",
                ExternalIdentity.external_subject_digest == subject_digest,
                ExternalIdentity.digest_key_version == key_version,
            )
            .order_by(ExternalIdentity.created_at, ExternalIdentity.id)
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def get_pending_by_subject(
        self,
        *,
        subject_digest: str,
        key_version: int,
        for_update: bool = False,
    ) -> PendingExternalIdentity | None:
        statement = select(PendingExternalIdentity).where(
            PendingExternalIdentity.provider == "GOOGLE",
            PendingExternalIdentity.external_subject_digest == subject_digest,
            PendingExternalIdentity.digest_key_version == key_version,
            PendingExternalIdentity.status == "PENDING",
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    def add_pending(self, pending: PendingExternalIdentity) -> None:
        self._session.add(pending)

    async def flush(self) -> None:
        await self._session.flush()
