"""Tenant-scoped conversation-session repository."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, cast, func, select

from app.models.agent import AgentRun
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class InteractionMetrics:
    today_count: int
    last_interaction_at: datetime | None
    local_date: date
    timezone: str
    as_of: datetime


class ConversationRepository(BaseRepository):
    async def interaction_metrics_by_elder(
        self, elder_ids: list[UUID], as_of: datetime
    ) -> dict[UUID, InteractionMetrics]:
        """Count completed response sessions, not requests, runs or transcript rows.

        EXISTS prevents multiple runs/retries from multiplying a session. Only
        metadata is read; local calendar dates use the persisted Elder timezone.
        Invalid timezones fail the request instead of silently changing the day.
        """
        if not elder_ids:
            return {}
        completed_response = (
            select(AgentRun.agent_run_id)
            .where(
                AgentRun.session_id == ConversationSession.id,
                AgentRun.tenant_id == self._tenant_id,
                AgentRun.elder_id == ConversationSession.elder_id,
                AgentRun.result_status.in_(["SUCCESS", "BLOCKED", "HUMAN_REVIEW"]),
                AgentRun.completed_at.is_not(None),
                AgentRun.completed_at <= as_of,
            )
            .exists()
        )
        local_day = cast(func.timezone(Elder.timezone, as_of), Date)
        ended_day = cast(func.timezone(Elder.timezone, ConversationSession.ended_at), Date)
        result = await self._session.execute(
            select(
                Elder.id,
                func.count(ConversationSession.id).filter(ended_day == local_day),
                func.max(ConversationSession.ended_at),
                local_day,
                Elder.timezone,
            )
            .outerjoin(
                ConversationSession,
                (ConversationSession.elder_id == Elder.id)
                & (ConversationSession.tenant_id == self._tenant_id)
                & (ConversationSession.state == "COMPLETED")
                & (ConversationSession.ended_at >= ConversationSession.started_at)
                & (ConversationSession.ended_at <= as_of)
                & completed_response,
            )
            .where(
                Elder.tenant_id == self._tenant_id,
                Elder.id.in_(elder_ids),
                Elder.status == "ACTIVE",
            )
            .group_by(Elder.id, Elder.timezone)
        )
        return {
            elder_id: InteractionMetrics(count, last, day, timezone, as_of)
            for elder_id, count, last, day, timezone in result.all()
        }

    async def get_by_id(self, session_id: UUID) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(
        self,
        session_id: UUID,
    ) -> ConversationSession | None:
        result = await self._session.execute(
            select(ConversationSession)
            .where(
                ConversationSession.id == session_id,
                ConversationSession.tenant_id == self._tenant_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_active_for_consent_for_update(
        self,
        consent_id: UUID,
    ) -> list[ConversationSession]:
        result = await self._session.execute(
            select(ConversationSession)
            .where(
                ConversationSession.tenant_id == self._tenant_id,
                ConversationSession.consent_id == consent_id,
                ConversationSession.state.in_(
                    {
                        "CREATED",
                        "RECORDING",
                        "AWAITING_CONFIRMATION",
                        "PROCESSING",
                        "RESPONDING",
                    }
                ),
            )
            .with_for_update()
        )
        return list(result.scalars().all())

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
