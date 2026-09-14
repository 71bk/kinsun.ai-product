"""Bounded historical notes, scoped through the caller's current assignment."""

from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.deletion import hash_subject_ref
from app.models.care_assignment import CareAssignment
from app.models.deletion import DeletionRequest, DeletionTombstone
from app.models.elder import Elder
from app.models.service_record import ServiceRecord


class ServiceRecordRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self._session = session
        self._tenant_id = tenant_id

    async def previous(self, current: CareAssignment) -> ServiceRecord | None:
        # A retained row is not permission to reuse it. Until service-note deletion
        # policy is complete, any non-cancelled request/marker suppresses all history
        # for this subject, including legal holds and completed deletion requests.
        deletion = exists(
            select(DeletionRequest.id)
            .join(Elder, Elder.id == DeletionRequest.elder_id)
            .where(
                Elder.tenant_id == self._tenant_id,
                DeletionRequest.elder_id == current.elder_id,
                DeletionRequest.status != "CANCELLED",
            )
        )
        tombstone = exists(
            select(DeletionTombstone.deletion_tombstone_id).where(
                DeletionTombstone.tenant_id == self._tenant_id,
                or_(
                    DeletionTombstone.elder_id == current.elder_id,
                    DeletionTombstone.subject_ref_hash
                    == hash_subject_ref(self._tenant_id, current.elder_id),
                ),
            )
        )
        return await self._session.scalar(
            select(ServiceRecord)
            .join(CareAssignment, CareAssignment.id == ServiceRecord.assignment_id)
            .where(
                ServiceRecord.tenant_id == self._tenant_id,
                CareAssignment.tenant_id == self._tenant_id,
                ServiceRecord.elder_id == current.elder_id,
                CareAssignment.elder_id == current.elder_id,
                CareAssignment.care_unit_id == current.care_unit_id,
                ServiceRecord.worker_id == CareAssignment.worker_id,
                CareAssignment.id != current.id,
                CareAssignment.status == "COMPLETED",
                CareAssignment.service_end <= current.service_start,
                ServiceRecord.completed_at < current.service_start,
                ServiceRecord.completed_at >= CareAssignment.service_start,
                ServiceRecord.completed_at < CareAssignment.service_end,
                ServiceRecord.record_type == "SERVICE_NOTE",
                ServiceRecord.status == "COMPLETED",
                ServiceRecord.version == 1,
                ServiceRecord.assignment_version >= 1,
                ServiceRecord.assignment_version < CareAssignment.version,
                ~deletion,
                ~tombstone,
            )
            .order_by(
                CareAssignment.service_end.desc(),
                CareAssignment.service_start.desc(),
                ServiceRecord.completed_at.desc(),
                ServiceRecord.service_record_id.desc(),
            )
            .limit(1)
        )
