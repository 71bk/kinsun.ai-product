"""Tenant-safe deletion request and tombstone persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.deletion import hash_resource_ref
from app.models.deletion import DeletionJobItem, DeletionRequest, DeletionTombstone
from app.models.elder import Elder


class DeletionRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def add_request(self, request: DeletionRequest) -> None:
        self._session.add(request)

    def add_item(self, item: DeletionJobItem) -> None:
        self._session.add(item)

    async def get(
        self,
        *,
        elder_id: UUID,
        deletion_request_id: UUID,
        for_update: bool = False,
    ) -> DeletionRequest | None:
        stmt = (
            select(DeletionRequest)
            .join(Elder, DeletionRequest.elder_id == Elder.id)
            .where(
                DeletionRequest.id == deletion_request_id,
                DeletionRequest.elder_id == elder_id,
                Elder.tenant_id == self._tenant_id,
            )
        )
        if for_update:
            stmt = stmt.with_for_update(of=DeletionRequest)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_for_consent(
        self,
        *,
        elder_id: UUID,
        consent_id: UUID,
    ) -> DeletionRequest | None:
        result = await self._session.execute(
            select(DeletionRequest)
            .join(Elder, DeletionRequest.elder_id == Elder.id)
            .where(
                DeletionRequest.elder_id == elder_id,
                DeletionRequest.consent_id == consent_id,
                Elder.tenant_id == self._tenant_id,
            )
            .order_by(DeletionRequest.requested_at.desc(), DeletionRequest.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_items(
        self,
        *,
        elder_id: UUID,
        deletion_request_id: UUID,
        for_update: bool = False,
    ) -> list[DeletionJobItem]:
        stmt = (
            select(DeletionJobItem)
            .join(
                DeletionRequest,
                DeletionJobItem.deletion_request_id == DeletionRequest.id,
            )
            .join(Elder, DeletionRequest.elder_id == Elder.id)
            .where(
                DeletionJobItem.deletion_request_id == deletion_request_id,
                DeletionRequest.elder_id == elder_id,
                Elder.tenant_id == self._tenant_id,
            )
            .order_by(DeletionJobItem.system_of_record, DeletionJobItem.resource_type)
        )
        if for_update:
            stmt = stmt.with_for_update(of=DeletionJobItem)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add_tombstone(
        self,
        *,
        elder_id: UUID,
        deletion_request_id: UUID,
        subject_ref_hash: str,
        resource_type: str,
        resource_id_hash: str,
        deleted_at: datetime,
        policy_version: str,
        reason_code: str,
        retention_basis: str,
    ) -> None:
        stmt = (
            insert(DeletionTombstone)
            .values(
                tenant_id=self._tenant_id,
                elder_id=elder_id,
                deletion_request_id=deletion_request_id,
                subject_ref_hash=subject_ref_hash,
                resource_type=resource_type,
                resource_id_hash=resource_id_hash,
                deleted_at=deleted_at,
                policy_version=policy_version,
                reason_code=reason_code,
                retention_basis=retention_basis,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "resource_type", "resource_id_hash"]
            )
        )
        await self._session.execute(stmt)

    async def has_tombstone(self, *, resource_type: str, resource_id: UUID) -> bool:
        tombstone_id = await self._session.scalar(
            select(DeletionTombstone.deletion_tombstone_id).where(
                DeletionTombstone.tenant_id == self._tenant_id,
                DeletionTombstone.resource_type == resource_type.strip().upper(),
                DeletionTombstone.resource_id_hash == hash_resource_ref(resource_type, resource_id),
            )
        )
        return tombstone_id is not None
