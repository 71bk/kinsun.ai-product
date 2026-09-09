"""Assignment-bound, live-authorized, append-only professional notes."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError
from app.events.outbox_writer import write_outbox_entry
from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.service_record import ServiceRecord
from app.models.tenant import Tenant
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.service_record import CreateServiceRecordRequest, ServiceRecordResponse


class ServiceRecordService:
    def __init__(self, session: AsyncSession, actor: ActorContext):
        self.session = session
        self.actor = actor

    async def _authorize(self, assignment_id: UUID, action: str) -> tuple[CareAssignment, str]:
        actor = self.actor
        if actor.status != "ACTIVE" or actor.actor_role != "HOME_CARE_WORKER":
            raise NotFoundError("Resource not found")
        # Serializes submissions for the exact assignment, not another visit for this elder.
        assignment = await self.session.scalar(
            select(CareAssignment)
            .where(
                CareAssignment.id == assignment_id,
                CareAssignment.tenant_id == actor.tenant_id,
                CareAssignment.worker_id == actor.actor_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)  # After any lock wait, never client-controlled.
        if (
            assignment is None
            or assignment.status != "IN_PROGRESS"
            or not (assignment.service_start <= now < assignment.service_end)
            or not {"assignment:read", action}.issubset(assignment.service_scope or [])
        ):
            raise NotFoundError("Resource not found")
        membership = exists(
            select(ActorTenantMembership.id).where(
                ActorTenantMembership.actor_id == actor.actor_id,
                ActorTenantMembership.tenant_id == actor.tenant_id,
                ActorTenantMembership.role_code == "HOME_CARE_WORKER",
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    ActorTenantMembership.effective_to > now,
                ),
                or_(
                    ActorTenantMembership.care_unit_id.is_(None),
                    ActorTenantMembership.care_unit_id == assignment.care_unit_id,
                ),
            )
        )
        timezone = await self.session.scalar(
            select(Elder.timezone).where(
                Elder.id == assignment.elder_id,
                Elder.tenant_id == actor.tenant_id,
                Elder.status == "ACTIVE",
                exists(
                    select(Tenant.id).where(Tenant.id == actor.tenant_id, Tenant.status == "ACTIVE")
                ),
                exists(
                    select(Actor.id).where(
                        Actor.id == actor.actor_id,
                        Actor.status == "ACTIVE",
                        Actor.actor_type == "HOME_CARE_WORKER",
                    )
                ),
                exists(
                    select(CareUnit.id).where(
                        CareUnit.id == assignment.care_unit_id,
                        CareUnit.tenant_id == actor.tenant_id,
                        CareUnit.status == "ACTIVE",
                    )
                ),
                membership,
            )
        )
        if timezone is None:
            raise NotFoundError("Resource not found")
        return assignment, timezone

    async def _find(self, assignment: CareAssignment) -> ServiceRecord | None:
        return await self.session.scalar(
            select(ServiceRecord).where(
                ServiceRecord.tenant_id == self.actor.tenant_id,
                ServiceRecord.assignment_id == assignment.id,
                ServiceRecord.elder_id == assignment.elder_id,
                ServiceRecord.worker_id == self.actor.actor_id,
                ServiceRecord.record_type == "SERVICE_NOTE",
                ServiceRecord.version == 1,
                ServiceRecord.status == "COMPLETED",
            )
        )

    async def get(self, assignment_id: UUID) -> dict:
        assignment, _ = await self._authorize(assignment_id, "service_record:read")
        record = await self._find(assignment)
        if record is None:
            raise NotFoundError("Resource not found")
        return self._response(record)

    @staticmethod
    def _response(record: ServiceRecord) -> dict:
        values = {name: getattr(record, name) for name in ServiceRecordResponse.model_fields}
        values["content"] = record.content["note"]
        return ServiceRecordResponse.model_validate(values).model_dump(mode="json")

    async def create(
        self, assignment_id: UUID, request: CreateServiceRecordRequest, key: str, trace_id: str
    ) -> dict:
        assignment, timezone = await self._authorize(assignment_id, "service_record:write")
        # Authorization precedes replay. An expired/completed/revoked assignment cannot
        # retrieve the old success snapshot, even with its original idempotency key.
        idem = IdempotencyRepository(self.session, self.actor.tenant_id, self.actor.actor_id)
        replay = await idem.begin(
            key=key,
            operation="create_service_record",
            payload={
                "assignment_id": str(assignment_id),
                **request.model_dump(mode="json"),
            },
        )
        # The idempotency claim can wait independently; recheck live state after it.
        assignment, timezone = await self._authorize(assignment_id, "service_record:write")
        if replay.replayed:
            if replay.response_body is None or await self._find(assignment) is None:
                raise NotFoundError("Resource not found")
            return replay.response_body
        if assignment.version != request.expected_assignment_version:
            raise ConflictError("Care assignment version conflict")
        if (
            await self.session.scalar(
                select(ServiceRecord.service_record_id).where(
                    ServiceRecord.assignment_id == assignment.id,
                    ServiceRecord.record_type == "SERVICE_NOTE",
                )
            )
            is not None
        ):
            raise ConflictError("A formal service record already exists")
        try:
            service_date = assignment.service_start.astimezone(ZoneInfo(timezone)).date()
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConflictError("Service timezone is invalid") from exc
        now = datetime.now(UTC)
        if not assignment.service_start <= now < assignment.service_end:
            raise NotFoundError("Resource not found")
        record = ServiceRecord(
            tenant_id=self.actor.tenant_id,
            assignment_id=assignment.id,
            elder_id=assignment.elder_id,
            worker_id=self.actor.actor_id,
            service_date=service_date,
            service_timezone=timezone,
            record_type=request.record_type,
            content={"note": request.content},
            status="COMPLETED",
            version=1,
            assignment_version=assignment.version,
            created_at=now,
            completed_at=now,
        )
        self.session.add(record)
        await self.session.flush()
        await write_outbox_entry(
            self.session,
            event_type="care.service_record.completed.v1",
            aggregate_type="service_record",
            aggregate_id=record.service_record_id,
            aggregate_version=1,
            tenant_id=self.actor.tenant_id,
            elder_id=assignment.elder_id,
            actor_id=self.actor.actor_id,
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=key,
            classification="RESTRICTED",
            purpose=None,
            payload={
                "service_record_id": str(record.service_record_id),
                "assignment_id": str(assignment.id),
                "version": 1,
                "status": "COMPLETED",
            },
        )
        response = self._response(record)
        await idem.complete(
            key=key,
            resource_type="service_record",
            resource_id=record.service_record_id,
            response_status=201,
            response_body=response,
        )
        return response
