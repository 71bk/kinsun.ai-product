"""Persistence boundary for external-provider sign-in handoff resolution."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.line_identity import ExternalIdentity
from app.models.pending_identity import PendingExternalIdentity


class GoogleIdentityRepository:
    """Serialize provider-subject handoffs and store only keyed/token digests.

    The historical class name remains for import compatibility while the
    repository now serves both approved direct OIDC providers.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: Literal["KINSUN", "GOOGLE", "LINE"] = "GOOGLE",
    ) -> None:
        self._session = session
        self._provider = provider

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        lock_key = f"{self._provider.casefold()}-subject:v{key_version}:{subject_digest}"
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
                ExternalIdentity.provider == self._provider,
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
            PendingExternalIdentity.provider == self._provider,
            PendingExternalIdentity.external_subject_digest == subject_digest,
            PendingExternalIdentity.digest_key_version == key_version,
            PendingExternalIdentity.status == "PENDING",
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_pending_by_token_digest(
        self,
        token_digest: str,
        *,
        for_update: bool = False,
    ) -> PendingExternalIdentity | None:
        statement = select(PendingExternalIdentity).where(
            PendingExternalIdentity.token_digest == token_digest,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    def add_identity(self, identity: ExternalIdentity) -> None:
        self._session.add(identity)

    def add_pending(self, pending: PendingExternalIdentity) -> None:
        self._session.add(pending)

    async def flush(self) -> None:
        await self._session.flush()
