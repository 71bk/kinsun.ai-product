"""Authorized single-turn bridge from Core to the private Agent Runtime."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_runtime import AgentRuntimePort
from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.domain.consent import ConsentPurpose
from app.models.agent import AgentRun
from app.models.asr_gate import AsrGateEvidence
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.safety import SafetyEvaluation
from app.policies.memory_policy import (
    TRUSTED_SPEAKER_LEVELS,
    GatedVoiceTurnFacts,
    SourceSpeakerEvidence,
    derive_turn_speaker_evidence,
)
from app.repositories.care_event_repo import CareEventRepository
from app.repositories.elder_repo import ElderRepository
from app.repositories.memory_repo import MemoryRepository
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.schemas.conversation import CompanionTurnResponse
from app.services.asr_gate_service import AsrGateService
from app.services.authorization_service import authorize_elder
from app.services.care_event_rendering import render_reviewed_event
from app.services.care_event_service import CareEventService
from app.services.companion_request import build_companion_runtime_request
from app.services.consent_service import ConsentService
from app.services.conversation_service import ConversationService
from app.services.knowledge_intent import resolve_turn_purpose

_MAX_CONFIRMED_MEMORY_CONTEXT_ITEMS = 5
_MAX_VERIFIED_EVENT_CONTEXT_ITEMS = 5

_RESULT_STATUS_MAP = {
    "SUCCESS": "SUCCESS",
    "BLOCKED": "BLOCKED",
    "SAFE_FALLBACK": "HUMAN_REVIEW",
    "FAILED": "DEPENDENCY_FAILED",
}

_SAFETY_DECISION_MAP = {
    "ALLOW": "ALLOW",
    "BLOCK": "BLOCK",
    "SAFE_FALLBACK": "HUMAN_REVIEW",
    "HUMAN_REVIEW": "HUMAN_REVIEW",
}


def _runtime_uuid(value: str, prefix: str) -> UUID:
    raw = value.removeprefix(prefix)
    try:
        return UUID(raw)
    except ValueError as exc:
        raise ServiceUnavailableError("Agent runtime returned an invalid identifier") from exc


class CompanionService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        runtime_client: AgentRuntimePort,
        model_route: str,
    ) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._runtime_client = runtime_client
        self._model_route = model_route
        self._conversations = ConversationService(session, tenant_id)

    async def _trusted_profile(self, elder_id: UUID) -> tuple[str | None, str]:
        elder = await ElderRepository(self._session, self._tenant_id).get_by_id(elder_id)
        if elder is None:
            raise NotFoundError("Resource not found")
        preferred_address = elder.preferred_name.strip() if elder.preferred_name else None
        return preferred_address or None, elder.response_length_preference

    async def _confirmed_memory_context(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
        turn_purpose: str,
    ) -> list[dict[str, object]]:
        """Load only currently authorized, consented, confirmed memory context."""
        if turn_purpose != "BASIC_VOICE":
            return []
        try:
            await authorize_elder(
                self._session,
                actor_context,
                conversation.elder_id,
                "memory:read",
            )
            consent = await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.LONG_TERM_MEMORY,
            )
        except NotFoundError:
            return []

        settings = get_settings()
        if not settings.evidence_aware_memory:
            return []
        records = await MemoryRepository(
            self._session,
            self._tenant_id,
        ).list_active_context_for_elder(
            elder_id=conversation.elder_id,
            active_consent_id=consent.id,
            active_consent_version=consent.version,
            limit=_MAX_CONFIRMED_MEMORY_CONTEXT_ITEMS,
            allow_auto_low_risk_memory=settings.auto_low_risk_memory,
        )
        return [
            {
                "memory_id": str(record.memory_id),
                "version": record.version,
                "memory_type": record.memory_type,
                "content": record.content,
                "consent_version": record.consent_version,
            }
            for record in records
        ]

    async def _requested_outputs(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
        speaker_evidence: SourceSpeakerEvidence,
    ) -> list[str]:
        """Derive proposal scope from current Core authorization and consent."""
        try:
            await authorize_elder(
                self._session,
                actor_context,
                conversation.elder_id,
                "care_event:candidate:create",
            )
            await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
            )
        except NotFoundError:
            return []
        requested_outputs = ["event_candidate"]
        if speaker_evidence.verification_level not in TRUSTED_SPEAKER_LEVELS:
            return requested_outputs
        try:
            await authorize_elder(
                self._session,
                actor_context,
                conversation.elder_id,
                "memory:candidate:create",
            )
            await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.LONG_TERM_MEMORY,
            )
        except NotFoundError:
            return requested_outputs
        requested_outputs.append("memory_candidate")
        return requested_outputs

    async def _verified_event_context(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
        turn_purpose: str,
    ) -> list[dict[str, object]]:
        if turn_purpose != "BASIC_VOICE":
            return []
        try:
            await authorize_elder(
                self._session,
                actor_context,
                conversation.elder_id,
                "care_event:read",
            )
            consent = await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
            )
        except NotFoundError:
            return []
        records = await CareEventRepository(
            self._session,
            self._tenant_id,
        ).list_projected_verified_context_for_elder(
            elder_id=conversation.elder_id,
            max_consent_version=consent.version,
            limit=_MAX_VERIFIED_EVENT_CONTEXT_ITEMS,
        )
        return [
            {
                "event_id": str(record.event_id),
                "version": record.version,
                "event_type": record.event_type,
                "summary_text": render_reviewed_event(
                    record.event_type,
                    record.structured_payload,
                ),
                "consent_version": record.consent_version,
            }
            for record in records
        ]

    async def _authorize_asr_input(
        self,
        *,
        conversation: ConversationSession,
        input_text: str,
    ) -> AsrGateEvidence:
        settings = get_settings()
        if not settings.asr_gate_enabled:
            raise AuthenticationError("ASR input is unavailable")
        return await AsrGateService(
            self._session,
            self._tenant_id,
            digest_secret=settings.asr_gate_hmac_secret,
            confidence_threshold=settings.asr_gate_confidence_threshold,
            evidence_ttl_seconds=settings.asr_gate_evidence_ttl_seconds,
        ).authorize_agent_input(
            conversation=conversation,
            input_text=input_text,
        )

    async def _speaker_evidence(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
        turn_reference: str,
        asr_evidence: AsrGateEvidence | None,
    ) -> SourceSpeakerEvidence:
        """Resolve statement ownership once, for both the request and the write."""
        voice_turn: GatedVoiceTurnFacts | None = None
        if asr_evidence is not None:
            elder = await ElderRepository(self._session, self._tenant_id).get_by_id(
                conversation.elder_id
            )
            voice_turn = GatedVoiceTurnFacts(
                asr_gate_evidence_id=asr_evidence.id,
                initiator_actor_id=conversation.initiator_actor_id,
                elder_actor_id=elder.actor_id if elder is not None else None,
            )
        return derive_turn_speaker_evidence(
            input_mode=conversation.input_mode,
            actor_role=actor_context.actor_role,
            actor_id=actor_context.actor_id,
            session_id=conversation.id,
            turn_reference=turn_reference,
            voice_turn=voice_turn,
        )

    async def run_turn(
        self,
        *,
        conversation: ConversationSession,
        actor_context: ActorContext,
        input_text: str,
        correlation_id: str,
        idempotency_key: str,
        latency_budget_ms: int,
    ) -> CompanionTurnResponse:
        supplied_elder_id = conversation.elder_id
        conversation = await self._conversations.get_for_update(conversation.id)
        if conversation is None or conversation.elder_id != supplied_elder_id:
            raise NotFoundError("Resource not found")

        is_text_turn = conversation.input_mode == "text" and conversation.state == "CREATED"
        is_gated_voice_turn = (
            conversation.input_mode in {"voice", "voice_with_text_fallback"}
            and conversation.state == "PROCESSING"
        )
        if not is_text_turn and not is_gated_voice_turn:
            raise ConflictError("Companion turn is not ready for Agent Runtime")
        if not conversation.policy_version:
            raise ConflictError("Voice session has no policy version")
        asr_evidence: AsrGateEvidence | None = None
        if is_gated_voice_turn:
            asr_evidence = await self._authorize_asr_input(
                conversation=conversation,
                input_text=input_text,
            )

        request_id = f"req-{uuid5(NAMESPACE_URL, f'kinsun:companion:{idempotency_key}')}"
        agent_run_id = uuid5(NAMESPACE_URL, f"kinsun:agent-run:{idempotency_key}")
        agent_run_wire_id = f"run-{agent_run_id}"
        speaker_evidence = await self._speaker_evidence(
            conversation=conversation,
            actor_context=actor_context,
            turn_reference=str(agent_run_id),
            asr_evidence=asr_evidence,
        )
        requested_outputs = await self._requested_outputs(
            conversation=conversation,
            actor_context=actor_context,
            speaker_evidence=speaker_evidence,
        )
        # The Agent Runtime selects a retrieval profile from `purpose`
        # (rag_integration.RAG_PURPOSES) and does not infer intent itself, so an
        # information request has to be identified here or the knowledge base is
        # never consulted. Everyday conversation keeps BASIC_VOICE.
        turn_purpose = resolve_turn_purpose(input_text)
        confirmed_memories = await self._confirmed_memory_context(
            conversation=conversation,
            actor_context=actor_context,
            turn_purpose=turn_purpose,
        )
        verified_care_events = await self._verified_event_context(
            conversation=conversation,
            actor_context=actor_context,
            turn_purpose=turn_purpose,
        )
        preferred_address, response_length = await self._trusted_profile(conversation.elder_id)
        request_payload = build_companion_runtime_request(
            conversation=conversation,
            actor_context=actor_context,
            request_id=request_id,
            agent_run_wire_id=agent_run_wire_id,
            purpose=turn_purpose,
            preferred_address=preferred_address,
            response_length=response_length,
            input_text=input_text,
            confirmed_memories=confirmed_memories,
            verified_care_events=verified_care_events,
            requested_outputs=requested_outputs,
            latency_budget_ms=latency_budget_ms,
        )

        if is_text_turn:
            await self._conversations.transition(
                conversation=conversation,
                target_state="RECORDING",
                actor_id=actor_context.actor_id,
                trace_id=correlation_id,
                idempotency_key=idempotency_key,
            )
            await self._conversations.transition(
                conversation=conversation,
                target_state="PROCESSING",
                actor_id=actor_context.actor_id,
                trace_id=correlation_id,
                idempotency_key=idempotency_key,
            )

        started_at = datetime.now(UTC)
        agent_run = AgentRun(
            agent_run_id=agent_run_id,
            session_id=conversation.id,
            elder_id=conversation.elder_id,
            tenant_id=self._tenant_id,
            actor_id=actor_context.actor_id,
            agent_id="companion-agent",
            agent_version="1.0.0",
            result_status="RUNNING",
            model_id=self._model_route,
            prompt_version="m0-companion-v1",
            policy_version=conversation.policy_version,
            token_usage={},
            trace_id=conversation.trace_id,
            started_at=started_at,
        )
        self._session.add(agent_run)
        await self._session.flush()

        started_clock = perf_counter()
        runtime_result = await self._runtime_client.run(
            request_payload=request_payload,
            correlation_id=correlation_id,
        )
        latency_ms = max(0, round((perf_counter() - started_clock) * 1000))

        if (
            runtime_result.request_id != request_id
            or runtime_result.trace_id != conversation.trace_id
            or runtime_result.agent_run_id != agent_run_wire_id
        ):
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")

        await self._conversations.transition(
            conversation=conversation,
            target_state="RESPONDING",
            actor_id=actor_context.actor_id,
            trace_id=correlation_id,
            idempotency_key=idempotency_key,
        )

        if _runtime_uuid(runtime_result.agent_run_id, "run-") != agent_run_id:
            raise ServiceUnavailableError("Agent runtime response correlation mismatch")
        agent_run.agent_id = runtime_result.selected_agent
        agent_run.agent_version = runtime_result.schema_version
        agent_run.result_status = _RESULT_STATUS_MAP[runtime_result.result_status]
        agent_run.latency_ms = latency_ms
        agent_run.stop_reason = ",".join(runtime_result.reason_codes)[:160] or None
        agent_run.completed_at = datetime.now(UTC)

        consent = await self._session.get(ConsentGrant, conversation.consent_id)
        if consent is None:
            raise ServiceUnavailableError("Voice session consent snapshot is unavailable")
        self._session.add(
            SafetyEvaluation(
                agent_run_id=agent_run_id,
                policy_id=consent.policy_id,
                target_type="agent_output",
                target_id=conversation.id,
                decision=_SAFETY_DECISION_MAP[runtime_result.safety_result.decision],
                reason_codes=runtime_result.safety_result.reason_codes,
                flags={"risk_level": runtime_result.safety_result.risk_level},
            )
        )
        await self._session.flush()

        await self._conversations.transition(
            conversation=conversation,
            target_state="COMPLETED",
            actor_id=actor_context.actor_id,
            trace_id=correlation_id,
            idempotency_key=idempotency_key,
        )

        proposal = runtime_result.event_candidate_proposal
        memory_proposal = runtime_result.memory_candidate_proposal
        if (
            proposal is not None
            and "event_candidate" in requested_outputs
            and runtime_result.result_status == "SUCCESS"
            and runtime_result.safety_result.decision == "ALLOW"
        ):
            try:
                await authorize_elder(
                    self._session,
                    actor_context,
                    conversation.elder_id,
                    "care_event:candidate:create",
                )
            except NotFoundError:
                pass
            else:
                # CareEventService rechecks live extraction consent and validates
                # that the Core-owned source session completed successfully.
                await CareEventService(self._session, self._tenant_id).create_candidate(
                    elder_id=conversation.elder_id,
                    actor_id=actor_context.actor_id,
                    request=CreateCareEventCandidateRequest(
                        source_type="CONVERSATION_SESSION",
                        source_id=conversation.id,
                        source_version=1,
                        event_type=proposal.event_type,
                        event_time=proposal.event_time,
                        structured_payload=proposal.structured_payload,
                        evidence_refs=proposal.evidence_refs,
                        confidence_band=proposal.confidence_band,
                        review_requirement=proposal.review_requirement,
                        extractor_version=proposal.extractor_version,
                    ),
                    trace_id=correlation_id,
                    idempotency_key=f"event-candidate:{agent_run_id}",
                    memory_candidate_proposal=(
                        memory_proposal.as_payload()
                        if memory_proposal is not None and "memory_candidate" in requested_outputs
                        else None
                    ),
                    source_speaker_evidence=speaker_evidence,
                )

        return CompanionTurnResponse(
            session_id=conversation.id,
            agent_run_id=agent_run_id,
            trace_id=runtime_result.trace_id,
            context_manifest_id=runtime_result.context_manifest_id,
            reply_text=runtime_result.reply_text,
            reply_language=runtime_result.reply_language,
            result_status=runtime_result.result_status,
            safety_decision=runtime_result.safety_result.decision,
            risk_level=runtime_result.safety_result.risk_level,
            reason_codes=runtime_result.reason_codes,
            model_route=self._model_route,
        )
