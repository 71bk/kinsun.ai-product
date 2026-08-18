"""Memory candidate, confirmation, correction, and deletion lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationDeniedError, ConflictError, ValidationError
from app.domain.state_machine import require_memory_transition
from app.events.outbox_writer import write_outbox_entry
from app.middleware.auth import ActorContext
from app.models.enums import ActorType
from app.models.memory import Memory, MemoryConfirmation, MemoryVersion
from app.policies.memory_policy import (
    CURRENT_MEMORY_POLICY_VERSION,
    TRUSTED_SPEAKER_LEVELS,
    evaluate_memory_candidate,
)
from app.policies.memory_retrieval import memory_content_digest
from app.repositories.elder_repo import ElderRepository
from app.repositories.memory_repo import MemoryRepository
from app.schemas.consent import ConsentPurpose
from app.schemas.memory import (
    ConfirmMemoryRequest,
    CreateMemoryCandidateRequest,
    UpdateMemoryRequest,
)
from app.services.consent_service import ConsentService


class MemoryService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._memories = MemoryRepository(session, tenant_id)

    async def get(self, elder_id: UUID, memory_id: UUID) -> Memory | None:
        return await self._memories.get(elder_id, memory_id)

    async def get_version(self, memory: Memory) -> MemoryVersion:
        return await self._memories.get_current_version(memory)

    async def list_for_elder(self, **kwargs) -> list[Memory]:
        return await self._memories.list_for_elder(**kwargs)

    async def create_candidate(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateMemoryCandidateRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        source = await self._memories.get_candidate_source_evidence(
            elder_id=elder_id,
            source_event_ids=request.source_event_ids,
        )
        if source is None:
            raise ValidationError(
                details=[
                    {
                        "field": "source_event_ids",
                        "reason": "VERIFIED_SINGLE_SOURCE_REQUIRED",
                    }
                ]
            )
        expected_source_proposal = {
            "memory_type": request.memory_type.value,
            "memory_kind": request.memory_kind.value,
            "normalized_content": request.normalized_content,
            "confirmation_question": request.confirmation_question,
            "extraction_confidence": request.extraction_confidence,
            "proposal_risk_hint": request.proposal_risk_hint.value,
            "extractor_version": request.extractor_version,
        }
        if source.memory_candidate_proposal != expected_source_proposal:
            raise ValidationError(
                details=[
                    {
                        "field": "source_event_ids",
                        "reason": "SOURCE_PROPOSAL_MISMATCH",
                    }
                ]
            )

        policy = evaluate_memory_candidate(
            memory_type=request.memory_type.value,
            memory_kind=request.memory_kind.value,
            normalized_content=request.normalized_content,
            confirmation_question=request.confirmation_question,
            extraction_confidence=request.extraction_confidence,
            possible_conflict=request.possible_conflict,
            speaker_verification_level=source.speaker_verification_level,
            speaker_evidence_reference=source.speaker_evidence_reference,
        )
        if not policy.create_memory or policy.status is None:
            raise ValidationError(
                details=[
                    {
                        "field": "memory_kind",
                        "reason": policy.reason_code,
                    }
                ]
            )

        now = datetime.now(UTC)
        content_digest = memory_content_digest(request.normalized_content)
        memory = Memory(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            memory_type=request.memory_type.value,
            memory_kind=request.memory_kind.value,
            actual_risk_level=policy.actual_risk_level,
            policy_decision=policy.policy_decision,
            policy_version=CURRENT_MEMORY_POLICY_VERSION,
            verification_level=policy.verification_level,
            required_verification=policy.required_verification,
            speaker_verification_level=source.speaker_verification_level,
            speaker_evidence_reference=source.speaker_evidence_reference,
            status=policy.status,
            current_version=1,
            activated_at=now if policy.status == "ACTIVE" else None,
            lifecycle_reason=policy.reason_code,
            consent_id=consent.id,
            consent_version=consent.version,
        )
        self._memories.add_memory(memory)
        await self._session.flush()
        self._memories.add_version(
            MemoryVersion(
                memory_id=memory.id,
                version=1,
                content=request.normalized_content,
                content_digest=content_digest,
                confirmation_question=request.confirmation_question,
                extractor_version=request.extractor_version,
                extraction_confidence=Decimal(str(request.extraction_confidence)).quantize(
                    Decimal("0.0001")
                ),
                source_event_ids=request.source_event_ids,
                source_session_id=source.source_session_id,
                source_turn_reference=source.source_turn_reference,
                proposal_risk_hint=request.proposal_risk_hint.value,
                version_status="ACTIVE",
                created_by_actor_id=actor_id,
            )
        )
        await self._session.flush()
        await self._write_event(
            event_type=(
                "memory.auto-activated.v1"
                if memory.status == "ACTIVE"
                else "memory.candidate-created.v1"
            ),
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def confirm(
        self,
        *,
        memory: Memory,
        actor_context: ActorContext,
        request: ConfirmMemoryRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        """Promote a candidate only after the authenticated elder confirms it.

        ``ELDER_UI`` is an explicit Core command made by the elder self. Core
        derives the actor and elder relationship from trusted server-side
        context and generates an opaque evidence reference from the request
        trace. Caregiver and legal-representative review may help prepare a
        candidate, but cannot satisfy the elder confirmation gate.

        VOICE confirmation remains unavailable until the voice path can create
        a versioned, consent-scoped record proving an authenticated affirmative
        answer to this exact candidate. A completed conversation alone is
        insufficient.
        """
        if memory.current_version != request.expected_candidate_version:
            raise ConflictError("Memory candidate version conflict")
        if (
            memory.policy_version != CURRENT_MEMORY_POLICY_VERSION
            or memory.actual_risk_level != "MEDIUM"
            or memory.policy_decision != "PENDING_ELDER_CONFIRMATION"
            or memory.required_verification != "ELDER_CONFIRMATION"
            or memory.speaker_verification_level not in TRUSTED_SPEAKER_LEVELS
            or not memory.speaker_evidence_reference
        ):
            raise ConflictError("Memory candidate policy evidence is stale or ineligible")
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=memory.elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        if (
            consent.id != memory.consent_id
            or consent.version != request.consent_version
            or consent.version != memory.consent_version
        ):
            raise ConflictError("Consent version changed; create a new candidate confirmation")

        if memory.status == "DEFERRED":
            require_memory_transition(memory.status, "PENDING_CONFIRMATION")
            memory.status = "PENDING_CONFIRMATION"

        await self._validate_confirmation_authority(
            memory=memory,
            actor_context=actor_context,
            request=request,
        )

        current = await self._memories.get_current_version(memory)
        if current.content_digest is None or current.content_digest != memory_content_digest(
            current.content
        ):
            raise ConflictError("Memory candidate content evidence is invalid")
        require_memory_transition(memory.status, "CONFIRMED")
        now = datetime.now(UTC)
        memory.status = "CONFIRMED"
        memory.confirmed_by_actor_id = actor_context.actor_id
        memory.confirmed_at = now
        memory.confirmation_method = request.confirmation_method
        memory.confirmation_session_id = None
        confirmation_evidence_reference = f"core-command:{trace_id}"
        memory.confirmation_evidence_ref = confirmation_evidence_reference
        memory.confirmed_version = memory.current_version
        memory.confirmed_content_digest = current.content_digest
        memory.policy_decision = "ELDER_CONFIRMED_MEDIUM"
        memory.verification_level = "ELDER_CONFIRMED"
        memory.lifecycle_reason = "ELDER_CONFIRMED_CURRENT_VERSION"
        self._memories.add_confirmation(
            MemoryConfirmation(
                tenant_id=self._tenant_id,
                elder_id=memory.elder_id,
                memory_id=memory.id,
                memory_version=memory.current_version,
                content_digest=current.content_digest,
                consent_id=consent.id,
                consent_version=consent.version,
                policy_version=CURRENT_MEMORY_POLICY_VERSION,
                decision_support_profile_id=None,
                decision_support_profile_version=None,
                confirmation_method=request.confirmation_method,
                response_intent="AFFIRM",
                confirmed_by_actor_id=actor_context.actor_id,
                confirmation_session_id=None,
                speaker_verification_level=memory.speaker_verification_level,
                speaker_evidence_reference=memory.speaker_evidence_reference,
                witness_actor_id=None,
                witness_evidence_reference=None,
                confirmation_evidence_reference=confirmation_evidence_reference,
                trace_id=trace_id,
                correlation_id=trace_id,
                idempotency_key=idempotency_key,
                confirmed_at=now,
            )
        )
        require_memory_transition(memory.status, "ACTIVE")
        memory.status = "ACTIVE"
        memory.activated_at = now
        await self._session.flush()
        await self._write_event(
            event_type="memory.confirmed.v1",
            memory=memory,
            actor_id=actor_context.actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def _validate_confirmation_authority(
        self,
        *,
        memory: Memory,
        actor_context: ActorContext,
        request: ConfirmMemoryRequest,
    ) -> None:
        """Allow only an authenticated elder to confirm their own candidate."""
        if request.confirmation_method == "VOICE":
            raise ValidationError(
                details=[
                    {
                        "field": "confirmation_method",
                        "reason": (
                            "VOICE confirmation is unavailable until the voice path can "
                            "produce authenticated candidate-specific affirmative evidence"
                        ),
                    }
                ]
            )

        if request.confirmation_method != "ELDER_UI" or actor_context.actor_role != ActorType.ELDER:
            raise AuthorizationDeniedError("Resource not found")
        elder = await ElderRepository(self._session, self._tenant_id).get_by_id(memory.elder_id)
        if elder is None or elder.actor_id != actor_context.actor_id:
            raise AuthorizationDeniedError("Resource not found")

    async def set_candidate_state(
        self,
        *,
        memory: Memory,
        target: str,
        actor_id: UUID,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        if memory.current_version != expected_version:
            raise ConflictError("Memory candidate version conflict")
        require_memory_transition(memory.status, target)
        memory.status = target
        await self._session.flush()
        await self._write_event(
            event_type=f"memory.{target.lower()}.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def update(
        self,
        *,
        memory: Memory,
        actor_id: UUID,
        request: UpdateMemoryRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=memory.elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        if memory.status not in {"ACTIVE", "INACTIVE"}:
            raise ConflictError("Only active or inactive memory can be corrected")
        if memory.current_version != request.expected_version:
            raise ConflictError("Memory version conflict")
        current = await self._memories.get_current_version(memory)
        now = datetime.now(UTC)
        current.version_status = "INACTIVE"
        current.valid_to = now
        if memory.status == "ACTIVE":
            require_memory_transition(memory.status, "INACTIVE")
        memory.status = "INACTIVE"
        memory.deactivated_at = now
        memory.actual_risk_level = "MEDIUM"
        memory.policy_decision = "NO_MEMORY"
        memory.policy_version = CURRENT_MEMORY_POLICY_VERSION
        memory.verification_level = "UNVERIFIED"
        memory.required_verification = "RESTRICTED"
        memory.speaker_verification_level = "UNKNOWN"
        memory.speaker_evidence_reference = None
        memory.confirmed_by_actor_id = None
        memory.confirmed_at = None
        memory.confirmation_method = None
        memory.confirmation_session_id = None
        memory.confirmation_evidence_ref = None
        memory.confirmed_version = None
        memory.confirmed_content_digest = None
        memory.lifecycle_reason = "CONTENT_CORRECTED_NEEDS_REVIEW"
        memory.current_version += 1
        self._memories.add_version(
            MemoryVersion(
                memory_id=memory.id,
                version=memory.current_version,
                content=request.content,
                content_digest=memory_content_digest(request.content),
                confirmation_question=None,
                extractor_version=None,
                extraction_confidence=None,
                source_event_ids=current.source_event_ids,
                source_session_id=None,
                source_turn_reference=None,
                proposal_risk_hint=None,
                version_status="ACTIVE",
                created_by_actor_id=actor_id,
                supersedes_version_id=current.memory_version_id,
            )
        )
        await self._session.flush()
        await self._write_event(
            event_type="memory.corrected.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def delete(
        self,
        *,
        memory: Memory,
        actor_id: UUID,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        if memory.current_version != expected_version:
            raise ConflictError("Memory version conflict")
        require_memory_transition(memory.status, "DELETED")
        now = datetime.now(UTC)
        memory.status = "DELETED"
        memory.deleted_at = now
        memory.deactivated_at = now
        current = await self._memories.get_current_version(memory)
        current.version_status = "DELETED"
        current.valid_to = now
        await self._session.flush()
        await self._write_event(
            event_type="memory.deleted.v1",
            memory=memory,
            actor_id=actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory

    async def _write_event(
        self,
        *,
        event_type: str,
        memory: Memory,
        actor_id: UUID,
        trace_id: str,
        idempotency_key: str,
    ) -> None:
        await write_outbox_entry(
            self._session,
            event_type=event_type,
            aggregate_type="memory",
            aggregate_id=memory.id,
            aggregate_version=memory.current_version,
            tenant_id=self._tenant_id,
            elder_id=memory.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY.value,
            consent_version=memory.consent_version,
            payload={
                "memory_id": str(memory.id),
                "status": memory.status,
                "version": memory.current_version,
                "confirmation_method": memory.confirmation_method,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
