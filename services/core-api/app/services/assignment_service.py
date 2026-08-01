"""Care-assignment lifecycle and scope service."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.domain.state_machine import require_assignment_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.repositories.care_assignment_repo import CareAssignmentRepository
from app.schemas.assignment import CreateAssignmentRequest


class AssignmentService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._assignments = CareAssignmentRepository(session, tenant_id)

    async def get(self, assignment_id: UUID) -> CareAssignment | None:
        return await self._assignments.get_by_id(assignment_id)

    async def list_for_worker(
        self,
        *,
        worker_id: UUID,
        service_date: date,
    ) -> list[CareAssignment]:
        start = datetime.combine(service_date, time.min, tzinfo=UTC)
        return await self._assignments.list_for_worker(
            worker_id=worker_id,
            window_start=start,
            window_end=start + timedelta(days=1),
        )

    async def create(
        self,
        *,
        actor_id: UUID,
        request: CreateAssignmentRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> CareAssignment:
        elder_exists = await self._session.scalar(
            select(Elder.id).where(
                Elder.id == request.elder_id,
                Elder.tenant_id == self._tenant_id,
            )
        )
        care_unit_exists = await self._session.scalar(
            select(CareUnit.id).where(
                CareUnit.id == request.care_unit_id,
                CareUnit.tenant_id == self._tenant_id,
                CareUnit.status == "ACTIVE",
            )
        )
        now = datetime.now(UTC)
        worker_exists = await self._session.scalar(
            select(Actor.id)
            .join(
                ActorTenantMembership,
                ActorTenantMembership.actor_id == Actor.id,
            )
            .where(
                Actor.id == request.worker_actor_id,
                Actor.actor_type == "HOME_CARE_WORKER",
                Actor.status == "ACTIVE",
                ActorTenantMembership.tenant_id == self._tenant_id,
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    now < ActorTenantMembership.effective_to,
                ),
            )
        )
        if not all((elder_exists, care_unit_exists, worker_exists)):
            raise ValidationError(
                details=[
                    {
                        "field": "assignment_scope",
                        "reason": "elder, care unit, and active worker must be valid",
                    }
                ]
            )

        assignment = CareAssignment(
            tenant_id=self._tenant_id,
            care_unit_id=request.care_unit_id,
            elder_id=request.elder_id,
            worker_id=request.worker_actor_id,
            service_start=request.service_start,
            service_end=request.service_end,
            service_scope=request.allowed_data_scopes,
            status="DRAFT",
            version=1,
        )
        self._assignments.add(assignment)
        await self._session.flush()
        await self._write_event(
            event_type="care.assignment.created.v1",
            assignment=assignment,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return assignment

    async def transition(
        self,
        *,
        assignment: CareAssignment,
        target: str,
        actor_id: UUID,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> CareAssignment:
        if assignment.version != expected_version:
            raise ConflictError("Care assignment version conflict")
        require_assignment_transition(assignment.status, target)
        now = datetime.now(UTC)
        if target == "IN_PROGRESS" and not (
            assignment.service_start <= now < assignment.service_end
        ):
            raise ConflictError("Assignment can start only inside its service window")
        assignment.status = target
        assignment.version += 1
        await self._session.flush()
        event_type = {
            "CONFIRMED": "care.assignment.confirmed.v1",
            "IN_PROGRESS": "care.assignment.started.v1",
            "COMPLETED": "care.assignment.completed.v1",
            "CANCELLED": "care.assignment.cancelled.v1",
            "EXPIRED": "care.assignment.expired.v1",
        }[target]
        await self._write_event(
            event_type=event_type,
            assignment=assignment,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return assignment

    async def _write_event(
        self,
        *,
        event_type: str,
        assignment: CareAssignment,
        actor_id: UUID,
        trace_id: str,
        idempotency_key: str,
    ) -> None:
        await write_outbox_entry(
            self._session,
            event_type=event_type,
            aggregate_type="care_assignment",
            aggregate_id=assignment.id,
            aggregate_version=assignment.version,
            tenant_id=self._tenant_id,
            elder_id=assignment.elder_id,
            actor_id=actor_id,
            purpose=None,
            payload={
                "assignment_id": str(assignment.id),
                "worker_actor_id": str(assignment.worker_id),
                "status": assignment.status,
                "version": assignment.version,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
            classification="CONFIDENTIAL",
        )
