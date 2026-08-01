"""Tenant-scoped conversation-session repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.conversation import ConversationSession
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository):
    async def get_by_id(self, session_id: UUID) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_elder(
        self,
        session_id: UUID,
        elder_id: UUID,
    ) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.elder_id == elder_id,
                ConversationSession.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    def add(self, conversation: ConversationSession) -> None:
        self._session.add(conversation)
