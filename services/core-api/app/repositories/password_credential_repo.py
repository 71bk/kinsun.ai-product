"""Persistence boundary for Kinsun password credentials."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.password_credential import PasswordCredential


class PasswordCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_actor(
        self,
        actor_id: UUID,
        *,
        for_update: bool = False,
    ) -> PasswordCredential | None:
        statement = select(PasswordCredential).where(
            PasswordCredential.actor_id == actor_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    def add(self, credential: PasswordCredential) -> None:
        self._session.add(credential)

    async def flush(self) -> None:
        await self._session.flush()
