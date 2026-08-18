"""Tenant-scoped confirmed-memory persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.models.care_event import CareEvent, CareEventVersion
from app.models.graph_projection import GraphProjectionRecord
from app.models.memory import Memory, MemoryConfirmation, MemoryVersion
from app.policies.memory_retrieval import (
    CURRENT_MEMORY_POLICY_VERSION,
    MemoryTrustEvidence,
    evaluate_memory_trust,
)
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class ConfirmedMemoryContextRecord:
    """Minimal current memory data that may cross the private Agent boundary."""

    memory_id: UUID
    version: int
    memory_type: str
    content: str
    consent_version: int


@dataclass(frozen=True)
class MemoryCandidateSourceEvidence:
    """Current verified CareEvent evidence used for one Memory proposal."""

    source_session_id: UUID | None
    source_turn_reference: str
    speaker_verification_level: str
    speaker_evidence_reference: str | None
    memory_candidate_proposal: dict | None


class MemoryRepository(BaseRepository):
    def add_memory(self, memory: Memory) -> None:
        self._session.add(memory)

    def add_version(self, version: MemoryVersion) -> None:
        self._session.add(version)

    def add_confirmation(self, confirmation: MemoryConfirmation) -> None:
        self._session.add(confirmation)

    async def get(self, elder_id: UUID, memory_id: UUID) -> Memory | None:
        result = await self._session.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.elder_id == elder_id,
                Memory.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(self, memory: Memory) -> MemoryVersion:
        result = await self._session.execute(
            select(MemoryVersion).where(
                MemoryVersion.memory_id == memory.id,
                MemoryVersion.version == memory.current_version,
            )
        )
        return result.scalar_one()

    async def get_candidate_source_evidence(
        self,
        *,
        elder_id: UUID,
        source_event_ids: list[UUID],
    ) -> MemoryCandidateSourceEvidence | None:
        """Resolve one current, reviewed source without trusting request metadata."""
        unique_ids = set(source_event_ids)
        if len(source_event_ids) != 1 or len(unique_ids) != 1:
            return None
        result = await self._session.execute(
            select(
                CareEvent.id,
                CareEvent.current_version,
                CareEvent.source_session_id,
                CareEventVersion.speaker_verification_level,
                CareEventVersion.speaker_evidence_reference,
                CareEventVersion.memory_candidate_proposal,
            )
            .join(
                CareEventVersion,
                and_(
                    CareEventVersion.event_id == CareEvent.id,
                    CareEventVersion.version == CareEvent.current_version,
                ),
            )
            .where(
                CareEvent.id.in_(unique_ids),
                CareEvent.elder_id == elder_id,
                CareEvent.tenant_id == self._tenant_id,
                CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        return MemoryCandidateSourceEvidence(
            source_session_id=row[2],
            source_turn_reference=f"care-event:{row[0]}:v{row[1]}",
            speaker_verification_level=row[3] or "UNKNOWN",
            speaker_evidence_reference=row[4],
            memory_candidate_proposal=row[5],
        )

    async def list_for_deletion(self, *, elder_id: UUID) -> list[Memory]:
        result = await self._session.execute(
            select(Memory)
            .where(
                Memory.elder_id == elder_id,
                Memory.tenant_id == self._tenant_id,
            )
            .order_by(Memory.id)
            .with_for_update()
        )
        return list(result.scalars().all())

    async def list_versions_for_deletion(
        self,
        *,
        memory_ids: list[UUID],
    ) -> list[MemoryVersion]:
        if not memory_ids:
            return []
        result = await self._session.execute(
            select(MemoryVersion)
            .where(MemoryVersion.memory_id.in_(memory_ids))
            .order_by(MemoryVersion.memory_id, MemoryVersion.version)
            .with_for_update()
        )
        return list(result.scalars().all())

    async def list_for_elder(
        self,
        *,
        elder_id: UUID,
        statuses: list[str],
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> list[Memory]:
        stmt = select(Memory).where(
            Memory.elder_id == elder_id,
            Memory.tenant_id == self._tenant_id,
            Memory.status.in_(statuses),
        )
        if cursor:
            created_at, memory_id = cursor
            stmt = stmt.where(
                or_(
                    Memory.created_at < created_at,
                    and_(
                        Memory.created_at == created_at,
                        Memory.id < memory_id,
                    ),
                )
            )
        result = await self._session.execute(
            stmt.order_by(Memory.created_at.desc(), Memory.id.desc()).limit(limit + 1)
        )
        return list(result.scalars().all())

    async def list_active_context_for_elder(
        self,
        *,
        elder_id: UUID,
        active_consent_id: UUID,
        active_consent_version: int,
        limit: int,
        current_policy_version: str = CURRENT_MEMORY_POLICY_VERSION,
        allow_auto_low_risk_memory: bool = False,
    ) -> list[ConfirmedMemoryContextRecord]:
        """Return only bounded records that pass the Spec 18 final gate."""
        candidate_limit = min(max(limit * 4, limit), 64)
        matching_confirmation_exists = (
            select(MemoryConfirmation.memory_confirmation_id)
            .where(
                MemoryConfirmation.tenant_id == self._tenant_id,
                MemoryConfirmation.elder_id == elder_id,
                MemoryConfirmation.memory_id == Memory.id,
                MemoryConfirmation.memory_version == Memory.current_version,
                MemoryConfirmation.content_digest == MemoryVersion.content_digest,
                MemoryConfirmation.consent_id == Memory.consent_id,
                MemoryConfirmation.consent_version == Memory.consent_version,
                MemoryConfirmation.policy_version == Memory.policy_version,
                MemoryConfirmation.response_intent == "AFFIRM",
                MemoryConfirmation.confirmation_method == Memory.confirmation_method,
                MemoryConfirmation.confirmed_by_actor_id == Memory.confirmed_by_actor_id,
                MemoryConfirmation.confirmation_session_id == Memory.confirmation_session_id,
                MemoryConfirmation.confirmed_at == Memory.confirmed_at,
                MemoryConfirmation.speaker_verification_level == Memory.speaker_verification_level,
                MemoryConfirmation.speaker_evidence_reference == Memory.speaker_evidence_reference,
                MemoryConfirmation.confirmation_evidence_reference
                == Memory.confirmation_evidence_ref,
            )
            .exists()
        )
        result = await self._session.execute(
            select(
                Memory.id,
                Memory.current_version,
                Memory.memory_type,
                MemoryVersion.content,
                Memory.consent_version,
                MemoryVersion.content_digest,
                Memory.memory_kind,
                Memory.consent_id,
                Memory.policy_version,
                Memory.policy_decision,
                Memory.actual_risk_level,
                Memory.verification_level,
                Memory.required_verification,
                Memory.speaker_verification_level,
                Memory.speaker_evidence_reference,
                Memory.confirmed_version,
                Memory.confirmed_content_digest,
                Memory.confirmation_method,
                Memory.confirmation_evidence_ref,
                Memory.confirmed_by_actor_id,
                Memory.confirmed_at,
                matching_confirmation_exists.label("matching_confirmation_exists"),
            )
            .join(
                MemoryVersion,
                and_(
                    MemoryVersion.memory_id == Memory.id,
                    MemoryVersion.version == Memory.current_version,
                ),
            )
            .join(
                GraphProjectionRecord,
                and_(
                    GraphProjectionRecord.source_type == "memory",
                    GraphProjectionRecord.source_id == Memory.id,
                    GraphProjectionRecord.source_version == Memory.current_version,
                    GraphProjectionRecord.projection_status == "SYNCED",
                    GraphProjectionRecord.graph_key.is_not(None),
                ),
            )
            .where(
                Memory.elder_id == elder_id,
                Memory.tenant_id == self._tenant_id,
                Memory.status == "ACTIVE",
                Memory.deleted_at.is_(None),
                Memory.consent_id == active_consent_id,
                Memory.consent_version == active_consent_version,
                Memory.policy_version == current_policy_version,
                MemoryVersion.version_status == "ACTIVE",
                MemoryVersion.valid_from <= func.now(),
                or_(MemoryVersion.valid_to.is_(None), MemoryVersion.valid_to > func.now()),
                func.char_length(MemoryVersion.content).between(1, 500),
            )
            .order_by(Memory.updated_at.desc(), Memory.id.desc())
            .limit(candidate_limit)
        )
        trusted: list[ConfirmedMemoryContextRecord] = []
        for row in result.all():
            decision = evaluate_memory_trust(
                MemoryTrustEvidence(
                    version=row[1],
                    content=row[3],
                    content_digest=row[5],
                    memory_kind=row[6],
                    consent_id_present=row[7] is not None,
                    policy_version=row[8],
                    policy_decision=row[9],
                    actual_risk_level=row[10],
                    verification_level=row[11],
                    required_verification=row[12],
                    speaker_verification_level=row[13],
                    speaker_evidence_reference=row[14],
                    confirmed_version=row[15],
                    confirmed_content_digest=row[16],
                    confirmation_method=row[17],
                    confirmation_evidence_reference=row[18],
                    confirmed_by_present=row[19] is not None,
                    confirmed_at_present=row[20] is not None,
                    confirmation_record_present=bool(row[21]) if len(row) > 21 else False,
                ),
                current_policy_version=current_policy_version,
                allow_auto_low_risk_memory=allow_auto_low_risk_memory,
            )
            if not decision.allowed:
                continue
            trusted.append(
                ConfirmedMemoryContextRecord(
                    memory_id=row[0],
                    version=row[1],
                    memory_type=row[2],
                    content=row[3],
                    consent_version=row[4],
                )
            )
            if len(trusted) == limit:
                break
        return trusted
