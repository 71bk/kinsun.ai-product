"""Conversation-session lifecycle service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.domain.state_machine import require_session_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.conversation import ConversationSession
from app.models.policy import PolicyRegistry
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.consent import ConsentPurpose
from app.schemas.conversation import CreateVoiceSessionRequest
from app.services.consent_service import ConsentService


class ConversationService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._repository = ConversationRepository(session, tenant_id)

    async def get(self, session_id: UUID) -> ConversationSession | None:
        return await self._repository.get_by_id(session_id)

    async def create(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        actor_role: str,
        request: CreateVoiceSessionRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> ConversationSession:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.BASIC_VOICE,
        )
        policy = await self._session.get(PolicyRegistry, consent.policy_id)
        initiator_type = {
            "ELDER": "ELDER",
            "FAMILY_MEMBER": "FAMILY",
            "SYSTEM_SERVICE": "SYSTEM",
        }.get(actor_role, "CAREGIVER")
        conversation = ConversationSession(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            initiator_actor_id=actor_id,
            initiator_type=initiator_type,
            language_route=request.language_preference.value,
            state="CREATED",
            trace_id=trace_id,
            consent_id=consent.id,
            consent_version=consent.version,
            policy_version=policy.version if policy is not None else None,
        )
        self._repository.add(conversation)
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="conversation.session.created.v1",
            aggregate_type="conversation_session",
            aggregate_id=conversation.id,
            aggregate_version=1,
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.BASIC_VOICE.value,
            consent_version=consent.version,
            payload={
                "session_id": str(conversation.id),
                "state": conversation.state,
                "language_route": conversation.language_route,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return conversation

    async def transition(
        self,
        *,
        conversation: ConversationSession,
        target_state: str,
        actor_id: UUID,
        trace_id: str,
        idempotency_key: str,
    ) -> ConversationSession:
        if target_state not in {"CANCELLED", "FAILED"}:
            active_consent = await ConsentService(
                self._session,
                self._tenant_id,
            ).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.BASIC_VOICE,
            )
            if (
                active_consent.id != conversation.consent_id
                or active_consent.version != conversation.consent_version
            ):
                raise ConflictError("Voice session consent version is no longer active")
        require_session_transition(conversation.state, target_state)
        conversation.state = target_state
        if target_state in {"COMPLETED", "CANCELLED", "FAILED"}:
            conversation.ended_at = datetime.now(UTC)
        await self._session.flush()
        if target_state == "COMPLETED":
            await write_outbox_entry(
                self._session,
                event_type="conversation.session.completed.v1",
                aggregate_type="conversation_session",
                aggregate_id=conversation.id,
                aggregate_version=1,
                tenant_id=self._tenant_id,
                elder_id=conversation.elder_id,
                actor_id=actor_id,
                purpose=ConsentPurpose.BASIC_VOICE.value,
                consent_version=conversation.consent_version,
                payload={
                    "session_id": str(conversation.id),
                    "state": target_state,
                },
                trace_id=trace_id,
                correlation_id=conversation.trace_id,
                idempotency_key=idempotency_key,
            )
        return conversation
