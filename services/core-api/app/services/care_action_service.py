"""Professional-confirmed Care Action lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.state_machine import require_care_action_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.care_action import CareAction
from app.models.care_event import CareEvent
from app.repositories.care_action_repo import CareActionRepository
from app.schemas.care_action import CreateCareActionRequest, UpdateCareActionRequest

PROFESSIONAL_CARE_ROLES = frozenset({"DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"})


class CareActionService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._actions = CareActionRepository(session, tenant_id)

    @staticmethod
    def require_professional(actor_context: ActorContext) -> None:
        if actor_context.actor_role not in PROFESSIONAL_CARE_ROLES:
            raise NotFoundError("Resource not found")

    async def get(self, elder_id: UUID, care_action_id: UUID) -> CareAction | None:
        return await self._actions.get(elder_id, care_action_id)

    async def list_for_elder(self, **kwargs) -> list[CareAction]:
        return await self._actions.list_for_elder(**kwargs)

    async def create(
        self,
        *,
        elder_id: UUID,
        actor_context: ActorContext,
        request: CreateCareActionRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> CareAction:
        self.require_professional(actor_context)
        assignee_id = request.assignee_actor_id or actor_context.actor_id
        if assignee_id != actor_context.actor_id:
            raise ValidationError(
                details=[
                    {
                        "field": "assignee_actor_id",
                        "reason": "the first Care Action slice supports only self-assignment",
                    }
                ]
            )
        now = datetime.now(UTC)
        if request.due_at <= now:
            raise ValidationError(
                details=[{"field": "due_at", "reason": "due_at must be in the future"}]
            )
        await self._require_formal_source_events(elder_id, request.related_event_ids)

        action = CareAction(
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            action_type=request.action_type,
            title=request.title.strip(),
            description=request.description.strip() if request.description else None,
            trigger_reason=request.trigger_reason.strip(),
            related_event_ids=request.related_event_ids,
            assignee_actor_id=assignee_id,
            due_at=request.due_at,
            priority=request.priority,
            status="OPEN",
            resolution=None,
            created_by_actor_id=actor_context.actor_id,
            version=1,
        )
        self._actions.add(action)
        await self._session.flush()
        await self._write_event(
            event_type="care.action.created.v1",
            action=action,
            actor_id=actor_context.actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return action

    async def transition(
        self,
        *,
        action: CareAction,
        actor_context: ActorContext,
        request: UpdateCareActionRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> CareAction:
        self.require_professional(actor_context)
        if action.assignee_actor_id != actor_context.actor_id:
            raise NotFoundError("Resource not found")
        if action.version != request.expected_version:
            raise ConflictError("Care Action version conflict")
        require_care_action_transition(action.status, request.status)
        if request.due_at is not None and request.due_at <= datetime.now(UTC):
            raise ValidationError(
                details=[{"field": "due_at", "reason": "due_at must be in the future"}]
            )

        await CareAction.apply_optimistic_update(
            self._session,
            action,
            request.expected_version,
        )
        action.status = request.status
        action.resolution = request.resolution.strip() if request.resolution else None
        if request.due_at is not None:
            action.due_at = request.due_at
        await self._session.flush()
        await self._write_event(
            event_type=f"care.action.{request.status.casefold()}.v1",
            action=action,
            actor_id=actor_context.actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return action

    async def _require_formal_source_events(
        self,
        elder_id: UUID,
        event_ids: list[UUID],
    ) -> None:
        count = await self._session.scalar(
            select(func.count())
            .select_from(CareEvent)
            .where(
                CareEvent.id.in_(event_ids),
                CareEvent.elder_id == elder_id,
                CareEvent.tenant_id == self._tenant_id,
                CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
            )
        )
        if count != len(event_ids):
            raise ValidationError(
                details=[
                    {
                        "field": "related_event_ids",
                        "reason": "Care Actions require formal events from the same Elder scope",
                    }
                ]
            )

    async def _write_event(
        self,
        *,
        event_type: str,
        action: CareAction,
        actor_id: UUID,
        trace_id: str,
        idempotency_key: str,
    ) -> None:
        await write_outbox_entry(
            self._session,
            event_type=event_type,
            aggregate_type="care_action",
            aggregate_id=action.id,
            aggregate_version=action.version,
            tenant_id=self._tenant_id,
            elder_id=action.elder_id,
            actor_id=actor_id,
            payload={
                "care_action_id": str(action.id),
                "action_type": action.action_type,
                "assignee_actor_id": str(action.assignee_actor_id),
                "related_event_ids": [str(event_id) for event_id in action.related_event_ids],
                "due_at": action.due_at.isoformat() if action.due_at else None,
                "priority": action.priority,
                "status": action.status,
                "version": action.version,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
            classification="CONFIDENTIAL",
        )
