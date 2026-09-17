"""Core command for low-risk personal statements, separate from care records."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.consent import ConsentPurpose
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.memory import Memory, MemoryVersion
from app.policies.memory_retrieval import memory_content_digest
from app.policies.personal_memory import (
    PERSONAL_MEMORY_EXTRACTOR,
    PERSONAL_MEMORY_POLICY,
    PersonalStatement,
    extract_personal_statement,
)
from app.repositories.decision_support_repo import DecisionSupportProfileRepository
from app.repositories.memory_repo import MemoryRepository
from app.schemas.conversation import PersonalMemoryReceipt
from app.services.authorization_service import authorize_elder
from app.services.consent_service import ConsentService
from app.services.memory_service import MemoryService


class PersonalMemoryService:
    def __init__(self, session: AsyncSession, tenant_id: UUID):
        self.session = session
        self.tenant_id = tenant_id
        self.repo = MemoryRepository(session, tenant_id)

    async def _owner(self, elder_id: UUID, actor: ActorContext) -> Elder:
        result = await self.session.execute(
            select(Elder)
            .where(
                Elder.id == elder_id,
                Elder.tenant_id == self.tenant_id,
                Elder.actor_id == actor.actor_id,
            )
            .with_for_update()
        )
        elder = result.scalar_one_or_none()
        if elder is None or actor.actor_role != "ELDER" or actor.tenant_id != self.tenant_id:
            raise NotFoundError("Resource not found")
        return elder

    async def _profile(self, elder_id: UUID, statement: PersonalStatement):
        profile = await DecisionSupportProfileRepository(
            self.session, self.tenant_id
        ).resolve_for_memory(
            elder_id=elder_id,
            data_class=statement.memory_type,
        )
        if (
            not profile.usable
            or profile.mode != "STANDARD"
            or "LOW" not in profile.allowed_memory_risks
        ):
            return None
        return profile

    async def capture(
        self,
        *,
        conversation: ConversationSession,
        actor: ActorContext,
        text: str,
        turn_id: UUID,
        trace_id: str,
    ) -> list[PersonalMemoryReceipt]:
        settings = get_settings()
        statement = extract_personal_statement(text)
        if not (
            getattr(settings, "personal_memory_enabled", False)
            and settings.evidence_aware_memory
            and statement
        ):
            return []
        if (
            conversation.input_mode != "text"
            or conversation.state != "COMPLETED"
            or conversation.tenant_id != self.tenant_id
            or conversation.initiator_actor_id != actor.actor_id
            or actor.actor_role != "ELDER"
        ):
            return []
        try:
            await authorize_elder(
                self.session, actor, conversation.elder_id, "memory:candidate:create"
            )
            await self._owner(conversation.elder_id, actor)
            consent = await ConsentService(self.session, self.tenant_id).require_active(
                elder_id=conversation.elder_id,
                purpose=ConsentPurpose.LONG_TERM_MEMORY,
            )
        except NotFoundError:
            return []
        if consent.scope.get("personal_memory_auto_save") is not True:
            return []
        profile = await self._profile(conversation.elder_id, statement)
        if profile is None:
            return []
        result = await self.session.execute(
            select(Memory)
            .where(
                Memory.elder_id == conversation.elder_id,
                Memory.tenant_id == self.tenant_id,
                Memory.policy_version == PERSONAL_MEMORY_POLICY,
                Memory.memory_kind == statement.kind,
                Memory.status == "ACTIVE",
                Memory.consent_id == consent.id,
                Memory.consent_version == consent.version,
            )
            .order_by(Memory.id)
            .with_for_update()
        )
        existing = list(result.scalars().all())
        if len(existing) > 1:
            return []  # Never choose an arbitrary conflicting current record.
        memory = existing[0] if existing else None
        previous = await self.repo.get_current_version(memory) if memory else None
        if previous and previous.content == statement.content:
            return [
                PersonalMemoryReceipt(
                    memory_id=memory.id, version=memory.current_version, content=previous.content
                )
            ]
        now = datetime.now(UTC)
        if memory is None:
            memory = Memory(
                elder_id=conversation.elder_id,
                tenant_id=self.tenant_id,
                memory_type=statement.memory_type,
                memory_kind=statement.kind,
                policy_version=PERSONAL_MEMORY_POLICY,
                actual_risk_level="LOW",
                policy_decision="AUTO_ACTIVATED_LOW",
                verification_level="POLICY_VERIFIED",
                required_verification="NONE",
                speaker_verification_level="VERIFIED_ELDER",
                evidence_state="CURRENT",
                status="ACTIVE",
                current_version=1,
                activated_at=now,
                consent_id=consent.id,
                consent_version=consent.version,
            )
            self.repo.add_memory(memory)
        else:
            previous.version_status = "INACTIVE"
            previous.valid_to = now
            memory.current_version += 1
        memory.speaker_evidence_reference = (
            f"conversation-session:{conversation.id}:turn:{turn_id}:authenticated-text"
        )
        memory.decision_support_profile_id = profile.profile_id
        memory.decision_support_profile_version = profile.profile_version
        memory.lifecycle_reason = "SELF_STATED_PERSONAL_MEMORY"
        await self.session.flush()
        self.repo.add_version(
            MemoryVersion(
                memory_id=memory.id,
                version=memory.current_version,
                content=statement.content,
                content_digest=memory_content_digest(statement.content),
                extractor_version=PERSONAL_MEMORY_EXTRACTOR,
                extraction_confidence=Decimal("1.0000"),
                source_event_ids=[],
                source_session_id=conversation.id,
                source_turn_reference=str(turn_id),
                proposal_risk_hint="LOW",
                version_status="ACTIVE",
                created_by_actor_id=actor.actor_id,
                supersedes_version_id=previous.memory_version_id if previous else None,
            )
        )
        await self.session.flush()
        await self.session.refresh(memory, ["updated_at"])
        await MemoryService(self.session, self.tenant_id)._write_event(
            event_type="memory.auto-activated.v1" if previous is None else "memory.corrected.v1",
            memory=memory,
            actor_id=actor.actor_id,
            trace_id=trace_id,
            idempotency_key=f"personal-memory:{turn_id}",
        )
        return [
            PersonalMemoryReceipt(
                memory_id=memory.id, version=memory.current_version, content=statement.content
            )
        ]

    async def edit(
        self,
        *,
        memory: Memory,
        actor: ActorContext,
        content: str,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> Memory:
        await self._owner(memory.elder_id, actor)
        await self.session.refresh(memory, with_for_update=True)
        consent = await ConsentService(self.session, self.tenant_id).require_active(
            elder_id=memory.elder_id,
            purpose=ConsentPurpose.LONG_TERM_MEMORY,
        )
        statement = extract_personal_statement(content)
        if consent.scope.get("personal_memory_auto_save") is not True:
            raise NotFoundError("Resource not found")
        if not statement or statement.kind != memory.memory_kind:
            raise ValidationError(
                details=[
                    {"field": "content", "reason": "EXPLICIT_SAME_KIND_PERSONAL_STATEMENT_REQUIRED"}
                ]
            )
        profile = await self._profile(memory.elder_id, statement)
        settings = get_settings()
        if (
            not profile
            or not settings.personal_memory_enabled
            or not settings.evidence_aware_memory
        ):
            raise NotFoundError("Resource not found")
        if (
            memory.status != "ACTIVE"
            or memory.current_version != expected_version
            or memory.consent_id != consent.id
            or memory.consent_version != consent.version
        ):
            raise ConflictError("Memory version or consent changed")
        current = await self.repo.get_current_version(memory)
        current.version_status = "INACTIVE"
        current.valid_to = datetime.now(UTC)
        memory.current_version += 1
        memory.decision_support_profile_id = profile.profile_id
        memory.decision_support_profile_version = profile.profile_version
        memory.speaker_evidence_reference = (
            f"elder-ui:{actor.actor_id}:memory:{memory.id}:v{memory.current_version}"
        )
        self.repo.add_version(
            MemoryVersion(
                memory_id=memory.id,
                version=memory.current_version,
                content=statement.content,
                content_digest=memory_content_digest(statement.content),
                source_event_ids=[],
                source_session_id=current.source_session_id,
                source_turn_reference=current.source_turn_reference,
                extractor_version=PERSONAL_MEMORY_EXTRACTOR,
                extraction_confidence=Decimal("1.0000"),
                proposal_risk_hint="LOW",
                version_status="ACTIVE",
                created_by_actor_id=actor.actor_id,
                supersedes_version_id=current.memory_version_id,
            )
        )
        await self.session.flush()
        await self.session.refresh(memory, ["updated_at"])
        await MemoryService(self.session, self.tenant_id)._write_event(
            event_type="memory.corrected.v1",
            memory=memory,
            actor_id=actor.actor_id,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return memory
