"""Care-event candidate and human-review lifecycle."""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.consent import ConsentPurpose
from app.domain.state_machine import CARE_EVENT_REVIEW_STATES
from app.events.outbox_writer import write_outbox_entry
from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision
from app.models.summary import DailySummary, SummaryVersion
from app.policies.memory_policy import SourceSpeakerEvidence, evaluate_memory_candidate
from app.repositories.care_event_repo import CareEventRepository
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.care_event import (
    ConfidenceBand,
    CreateCareEventCandidateRequest,
    ReviewCareEventRequest,
)
from app.schemas.memory import CreateMemoryCandidateRequest
from app.services.authorization_service import authorize_elder
from app.services.consent_service import ConsentService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

CONFIDENCE_VALUES = {
    ConfidenceBand.LOW: Decimal("0.3000"),
    ConfidenceBand.MEDIUM: Decimal("0.6000"),
    ConfidenceBand.HIGH: Decimal("0.9000"),
}


class CareEventService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._events = CareEventRepository(session, tenant_id)

    async def get(
        self,
        elder_id: UUID,
        event_id: UUID,
        statuses: list[str] | None = None,
    ) -> CareEvent | None:
        return await self._events.get(elder_id, event_id, statuses)

    async def get_version(self, event: CareEvent) -> CareEventVersion:
        return await self._events.get_current_version(event)

    async def get_latest_review(self, event_id: UUID) -> ReviewDecision | None:
        return await self._events.get_latest_review(event_id)

    async def list_for_elder(self, **kwargs) -> list[CareEvent]:
        return await self._events.list_for_elder(**kwargs)

    async def create_candidate(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateCareEventCandidateRequest,
        trace_id: str,
        idempotency_key: str,
        memory_candidate_proposal: dict[str, Any] | None = None,
        source_speaker_evidence: SourceSpeakerEvidence | None = None,
    ) -> CareEvent:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
        )
        if request.source_type == "CONVERSATION_SESSION":
            conversation = await ConversationRepository(
                self._session,
                self._tenant_id,
            ).get_for_elder(request.source_id, elder_id)
            if conversation is None:
                raise NotFoundError("Source session not found")
            if conversation.state != "COMPLETED":
                raise ConflictError("Care-event extraction requires a completed session")

        speaker_evidence = source_speaker_evidence or SourceSpeakerEvidence(
            verification_level="UNKNOWN",
            evidence_reference=None,
            speaker_role=None,
            speaker_actor_id=None,
            verification_method="UNVERIFIED_SOURCE",
        )
        if memory_candidate_proposal is not None:
            try:
                await ConsentService(self._session, self._tenant_id).require_active(
                    elder_id=elder_id,
                    purpose=ConsentPurpose.LONG_TERM_MEMORY,
                )
            except NotFoundError:
                logger.info(
                    "memory proposal discarded before care-event persistence",
                    extra={"reason_code": "LONG_TERM_MEMORY_CONSENT_INACTIVE"},
                )
                memory_candidate_proposal = None
        if memory_candidate_proposal is not None:
            try:
                proposal_decision = evaluate_memory_candidate(
                    memory_type=str(memory_candidate_proposal["memory_type"]),
                    memory_kind=str(memory_candidate_proposal["memory_kind"]),
                    normalized_content=str(memory_candidate_proposal["normalized_content"]),
                    confirmation_question=str(memory_candidate_proposal["confirmation_question"]),
                    extraction_confidence=float(memory_candidate_proposal["extraction_confidence"]),
                    possible_conflict=False,
                    speaker_verification_level=speaker_evidence.verification_level,
                    speaker_evidence_reference=speaker_evidence.evidence_reference,
                )
            except (KeyError, TypeError, ValueError):
                proposal_decision = None
            if proposal_decision is None or not proposal_decision.create_memory:
                logger.info(
                    "memory proposal discarded before care-event persistence",
                    extra={
                        "reason_code": (
                            proposal_decision.reason_code
                            if proposal_decision is not None
                            else "INVALID_PROPOSAL"
                        )
                    },
                )
                memory_candidate_proposal = None

        event = CareEvent(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            source_session_id=request.source_id
            if request.source_type == "CONVERSATION_SESSION"
            else None,
            event_type=request.event_type.value,
            event_time=request.event_time,
            status="NEEDS_REVIEW",
            current_version=1,
            consent_version=consent.version,
        )
        self._events.add_event(event)
        await self._session.flush()
        self._events.add_version(
            CareEventVersion(
                event_id=event.id,
                version=1,
                structured_payload=request.structured_payload,
                memory_candidate_proposal=memory_candidate_proposal,
                evidence_text_ref=json.dumps(request.evidence_refs),
                confidence=CONFIDENCE_VALUES[request.confidence_band],
                speaker_role=speaker_evidence.speaker_role,
                speaker_actor_id=speaker_evidence.speaker_actor_id,
                speaker_verification_level=speaker_evidence.verification_level,
                speaker_verification_method=speaker_evidence.verification_method,
                speaker_evidence_reference=speaker_evidence.evidence_reference,
                created_by_actor_id=actor_id,
            )
        )
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="care.event.candidate-created.v1",
            aggregate_type="care_event",
            aggregate_id=event.id,
            aggregate_version=1,
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            consent_version=consent.version,
            payload={
                "event_id": str(event.id),
                "event_type": event.event_type,
                "status": event.status,
                "source_session_id": str(event.source_session_id)
                if event.source_session_id
                else None,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return event

    async def review(
        self,
        *,
        event: CareEvent,
        actor_context: ActorContext,
        request: ReviewCareEventRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> tuple[ReviewDecision, list[str]]:
        if event.status not in {"CANDIDATE", "NEEDS_REVIEW"}:
            raise ConflictError("Only candidate events can be reviewed")
        if event.current_version != request.expected_version:
            raise ConflictError("Care event version conflict")
        await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=event.elder_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
        )

        actor_id = actor_context.actor_id
        before_version = event.current_version
        current = await self._events.get_current_version(event)
        if request.decision == "CORRECT":
            event.current_version += 1
            self._events.add_version(
                CareEventVersion(
                    event_id=event.id,
                    version=event.current_version,
                    structured_payload=request.corrected_payload,
                    memory_candidate_proposal=None,
                    evidence_text_ref=current.evidence_text_ref,
                    confidence=current.confidence,
                    speaker_role=current.speaker_role,
                    speaker_actor_id=current.speaker_actor_id,
                    speaker_verification_level=current.speaker_verification_level,
                    speaker_verification_method=current.speaker_verification_method,
                    speaker_evidence_reference=current.speaker_evidence_reference,
                    created_by_actor_id=actor_id,
                    supersedes_version_id=current.event_version_id,
                )
            )
        event.status = CARE_EVENT_REVIEW_STATES[request.decision]
        review = ReviewDecision(
            target_type="CARE_EVENT",
            target_id=event.id,
            event_id=event.id,
            reviewer_actor_id=actor_id,
            decision=request.decision,
            reason_code=request.reason_code,
            before_version=before_version,
            after_version=event.current_version,
        )
        self._events.add_review(review)

        rebuild_required: list[str] = []
        if request.decision in {"CORRECT", "REJECT", "EXCLUDE"}:
            affected = select(SummaryVersion.summary_id).where(
                SummaryVersion.source_event_ids.contains([event.id])
            )
            await self._session.execute(
                update(DailySummary)
                .where(
                    DailySummary.tenant_id == self._tenant_id,
                    DailySummary.id.in_(affected),
                )
                .values(status="STALE")
            )
            rebuild_required = ["DAILY_SUMMARY"]

        await self._session.flush()
        if request.decision == "VERIFY" and current.memory_candidate_proposal is not None:
            await self._promote_memory_candidate(
                event=event,
                actor_context=actor_context,
                proposal=current.memory_candidate_proposal,
                trace_id=trace_id,
                idempotency_key=f"memory-candidate:{event.id}:{before_version}",
            )
        event_name = {
            "VERIFY": "verified",
            "CORRECT": "corrected",
            "REJECT": "rejected",
            "EXCLUDE": "rejected",
        }[request.decision]
        await write_outbox_entry(
            self._session,
            event_type=f"care.event.{event_name}.v1",
            aggregate_type="care_event",
            aggregate_id=event.id,
            aggregate_version=event.current_version,
            tenant_id=self._tenant_id,
            elder_id=event.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            consent_version=event.consent_version,
            payload={
                "event_id": str(event.id),
                "status": event.status,
                "version": event.current_version,
                "review_id": str(review.review_id),
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return review, rebuild_required

    async def _promote_memory_candidate(
        self,
        *,
        event: CareEvent,
        actor_context: ActorContext,
        proposal: dict[str, Any],
        trace_id: str,
        idempotency_key: str,
    ) -> None:
        """Create only a Candidate after live authorization, consent, and source checks."""
        try:
            await authorize_elder(
                self._session,
                actor_context,
                event.elder_id,
                "memory:candidate:create",
            )
            candidate_request = CreateMemoryCandidateRequest.model_validate(
                {
                    **proposal,
                    "source_event_ids": [event.id],
                    "possible_conflict": False,
                    "conflict_with_memory_ids": [],
                }
            )
            await MemoryService(self._session, self._tenant_id).create_candidate(
                elder_id=event.elder_id,
                actor_id=actor_context.actor_id,
                request=candidate_request,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
            )
        except NotFoundError:
            # Event review remains valid even if memory authority or consent was revoked.
            logger.info(
                "memory candidate promotion skipped",
                extra={"care_event_id": str(event.id), "reason_code": "MEMORY_GATE_CLOSED"},
            )
        except (PydanticValidationError, ValidationError):
            # A malformed stale proposal must never block the human event review.
            logger.warning(
                "memory candidate promotion skipped",
                extra={"care_event_id": str(event.id), "reason_code": "INVALID_PROPOSAL"},
            )
