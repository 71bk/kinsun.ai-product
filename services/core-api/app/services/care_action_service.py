"""Professional-confirmed Care Action lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.care_action import (
    CARE_EVENT_PROVENANCE_SCHEMA_VERSION,
    care_event_snapshot_sha256,
)
from app.domain.state_machine import require_care_action_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.care_action import CareAction, CareActionEventProvenance
from app.models.care_event import CareEvent, CareEventVersion
from app.repositories.care_action_repo import CareActionRepository
from app.repositories.care_event_repo import CareEventRepository
from app.schemas.care_action import CreateCareActionRequest, UpdateCareActionRequest

PROFESSIONAL_CARE_ROLES = frozenset({"DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"})


class CareActionService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._actions = CareActionRepository(session, tenant_id)
        self._events = CareEventRepository(session, tenant_id)

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
        expected_source_versions: dict[UUID, int] | None = None,
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
        source_events = await self._capture_formal_source_events(
            elder_id,
            request.related_event_ids,
        )
        if expected_source_versions is not None and any(
            expected_source_versions.get(event.id) != event_version.version
            for event, event_version in source_events
        ):
            raise ConflictError("Care Action candidate source event changed")

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
            source_event_provenance=[
                self._build_source_event_provenance(source_order, event, event_version)
                for source_order, (event, event_version) in enumerate(source_events)
            ],
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

    async def _capture_formal_source_events(
        self,
        elder_id: UUID,
        event_ids: list[UUID],
    ) -> list[tuple[CareEvent, CareEventVersion]]:
        sources = await self._events.list_formal_current_versions_for_update(
            elder_id=elder_id,
            event_ids=event_ids,
        )
        sources_by_event_id = {event.id: (event, version) for event, version in sources}
        if len(sources_by_event_id) != len(event_ids):
            raise ValidationError(
                details=[
                    {
                        "field": "related_event_ids",
                        "reason": "Care Actions require formal events from the same Elder scope",
                    }
                ]
            )
        return [sources_by_event_id[event_id] for event_id in event_ids]

    @staticmethod
    def _build_source_event_provenance(
        source_order: int,
        event: CareEvent,
        event_version: CareEventVersion,
    ) -> CareActionEventProvenance:
        return CareActionEventProvenance(
            source_order=source_order,
            event_id=event.id,
            event_version_id=event_version.event_version_id,
            event_version=event_version.version,
            event_type=event.event_type,
            event_time=event.event_time,
            source_status=event.status,
            snapshot_sha256=care_event_snapshot_sha256(
                event_id=event.id,
                event_version_id=event_version.event_version_id,
                event_version=event_version.version,
                event_type=event.event_type,
                event_time=event.event_time,
                source_status=event.status,
                structured_payload=event_version.structured_payload,
                evidence_text_ref=event_version.evidence_text_ref,
            ),
            snapshot_schema_version=CARE_EVENT_PROVENANCE_SCHEMA_VERSION,
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
                "source_event_provenance": [
                    {
                        "event_id": str(source.event_id),
                        "event_version_id": str(source.event_version_id),
                        "event_version": source.event_version,
                        "snapshot_sha256": source.snapshot_sha256,
                        "snapshot_schema_version": source.snapshot_schema_version,
                    }
                    for source in action.source_event_provenance
                ],
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
