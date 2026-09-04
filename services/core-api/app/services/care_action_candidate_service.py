"""Human-gated lifecycle for AI-proposed Care Actions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, ValidationError
from app.domain.care_action import (
    CARE_EVENT_PROVENANCE_SCHEMA_VERSION,
    care_event_snapshot_sha256,
)
from app.models.care_action import CareAction
from app.models.care_action_candidate import (
    CareActionCandidate,
    CareActionCandidateEventProvenance,
)
from app.models.care_event import CareEvent, CareEventVersion
from app.policies.care_action_candidate_policy import evaluate_care_action_candidate
from app.repositories.care_action_candidate_repo import CareActionCandidateRepository
from app.schemas.care_action import (
    AdoptCareActionCandidateRequest,
    AgentCareActionCandidateProposal,
    CreateCareActionRequest,
    DismissCareActionCandidateRequest,
)
from app.services.care_action_service import CareActionService


class CareActionCandidateService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._candidates = CareActionCandidateRepository(session, tenant_id)

    @staticmethod
    def require_professional(actor_context: ActorContext) -> None:
        CareActionService.require_professional(actor_context)

    async def get(
        self,
        elder_id: UUID,
        candidate_id: UUID,
        *,
        for_update: bool = False,
    ) -> CareActionCandidate | None:
        return await self._candidates.get(elder_id, candidate_id, for_update=for_update)

    async def list_for_elder(self, **kwargs) -> list[CareActionCandidate]:
        return await self._candidates.list_for_elder(**kwargs)

    async def create_from_verified_event(
        self,
        *,
        event: CareEvent,
        event_version: CareEventVersion,
        proposal_payload: dict[str, Any],
    ) -> CareActionCandidate:
        if event.status not in {"VERIFIED", "CORRECTED"}:
            raise ValidationError(
                details=[
                    {
                        "field": "source_event",
                        "reason": "Care Action candidates require a formal source event",
                    }
                ]
            )
        if event_version.version != event.current_version:
            raise ValidationError(
                details=[
                    {
                        "field": "source_event",
                        "reason": "Care Action candidates require the current event version",
                    }
                ]
            )
        try:
            proposal = AgentCareActionCandidateProposal.model_validate(proposal_payload)
        except PydanticValidationError as exc:
            raise ValidationError(
                details=[{"field": "proposal", "reason": "invalid candidate proposal"}]
            ) from exc
        decision = evaluate_care_action_candidate(
            proposal,
            source_event_type=event.event_type,
        )
        if not decision.accepted:
            raise ValidationError(details=[{"field": "proposal", "reason": decision.reason_code}])

        candidate = CareActionCandidate(
            tenant_id=self._tenant_id,
            elder_id=event.elder_id,
            action_type=proposal.action_type,
            suggested_title=proposal.suggested_title,
            trigger_reason=proposal.trigger_reason,
            suggested_due_at=proposal.suggested_due_at,
            priority=proposal.priority,
            status="PENDING_REVIEW",
            extractor_version=proposal.extractor_version,
            version=1,
            source_event_provenance=[
                CareActionCandidateEventProvenance(
                    source_order=0,
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
            ],
        )
        self._candidates.add(candidate)
        await self._session.flush()
        return candidate

    async def adopt(
        self,
        *,
        candidate: CareActionCandidate,
        actor_context: ActorContext,
        request: AdoptCareActionCandidateRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> tuple[CareActionCandidate, CareAction]:
        self.require_professional(actor_context)
        self._require_pending_version(candidate, request.expected_version)
        await CareActionCandidate.apply_optimistic_update(
            self._session,
            candidate,
            request.expected_version,
        )
        action = await CareActionService(self._session, self._tenant_id).create(
            elder_id=candidate.elder_id,
            actor_context=actor_context,
            request=CreateCareActionRequest(
                action_type=candidate.action_type,
                title=request.title or candidate.suggested_title,
                description=None,
                trigger_reason=candidate.trigger_reason,
                related_event_ids=[source.event_id for source in candidate.source_event_provenance],
                assignee_actor_id=actor_context.actor_id,
                due_at=request.due_at or candidate.suggested_due_at,
                priority=request.priority or candidate.priority,
            ),
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            expected_source_versions={
                source.event_id: source.event_version
                for source in candidate.source_event_provenance
            },
        )
        candidate.status = "ADOPTED"
        candidate.disposition_reason_code = "HUMAN_CONFIRMED"
        candidate.decided_by_actor_id = actor_context.actor_id
        candidate.decided_at = datetime.now(UTC)
        candidate.adopted_care_action_id = action.id
        await self._session.flush()
        return candidate, action

    async def dismiss(
        self,
        *,
        candidate: CareActionCandidate,
        actor_context: ActorContext,
        request: DismissCareActionCandidateRequest,
    ) -> CareActionCandidate:
        self.require_professional(actor_context)
        self._require_pending_version(candidate, request.expected_version)
        await CareActionCandidate.apply_optimistic_update(
            self._session,
            candidate,
            request.expected_version,
        )
        candidate.status = "REJECTED" if request.decision == "REJECT" else "EXCLUDED"
        candidate.disposition_reason_code = request.reason_code
        candidate.disposition_notes = request.notes
        candidate.decided_by_actor_id = actor_context.actor_id
        candidate.decided_at = datetime.now(UTC)
        candidate.adopted_care_action_id = None
        await self._session.flush()
        return candidate

    @staticmethod
    def _require_pending_version(candidate: CareActionCandidate, expected_version: int) -> None:
        if candidate.status != "PENDING_REVIEW":
            raise ConflictError("Care Action candidate is no longer pending")
        if candidate.version != expected_version:
            raise ConflictError("Care Action candidate version conflict")
