"""Voice-path speaker gate and memory proposal scope against a real database.

The Gate 1 five-run harness calls the Agent Runtime through Core's adapter with
a hand-built payload, so it hard-codes ``requested_outputs`` and never reaches
the Core seams that decide it. That is how a voice turn could stay
``SPEAKER_OWNERSHIP_UNVERIFIED`` for every session while Gate 1 stayed green.

These tests close that gap at the layer where the decision actually lives: real
``ElderRepository`` lookups, real ``authorize_elder`` and real ``ConsentService``
over seeded rows, for both the Spec 18 3.4 gated Elder-only session and the
sessions 6.2 keeps unverified.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.auth import ActorContext
from app.domain.consent import ConsentPurpose
from app.models.actor import Actor
from app.models.asr_gate import AsrGateEvidence
from app.models.consent import ConsentGrant
from app.models.conversation import ConversationSession
from app.models.elder import Elder
from app.models.policy import PolicyRegistry
from app.models.tenant import Tenant
from app.services.companion_service import CompanionService

SYNTHETIC_TRANSCRIPT = "我每天早餐都吃粥"


@dataclass(frozen=True)
class VoiceSeed:
    tenant_id: uuid.UUID
    elder_id: uuid.UUID
    elder_actor_id: uuid.UUID
    staff_actor_id: uuid.UUID
    elder_session_id: uuid.UUID
    staff_session_id: uuid.UUID


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _grant(
    *,
    elder_id: uuid.UUID,
    actor_id: uuid.UUID,
    policy_id: uuid.UUID,
    purpose: ConsentPurpose,
    granted_at: datetime,
) -> ConsentGrant:
    return ConsentGrant(
        id=uuid.uuid4(),
        elder_id=elder_id,
        purpose_code=purpose.value,
        status="GRANTED",
        version=1,
        granted_by_actor_id=actor_id,
        policy_id=policy_id,
        granted_at=granted_at,
        effective_at=granted_at,
    )


def _voice_session(
    *,
    session_id: uuid.UUID,
    tenant_id: uuid.UUID,
    elder_id: uuid.UUID,
    initiator_actor_id: uuid.UUID,
    initiator_type: str,
    consent_id: uuid.UUID,
    trace_id: str,
) -> ConversationSession:
    return ConversationSession(
        id=session_id,
        tenant_id=tenant_id,
        elder_id=elder_id,
        initiator_actor_id=initiator_actor_id,
        initiator_type=initiator_type,
        language_route="ZH_TW",
        input_mode="voice",
        state="PROCESSING",
        trace_id=trace_id,
        consent_id=consent_id,
        consent_version=1,
        policy_version="adr-0009+memory-policy-v1",
    )


def _accepted_asr_evidence(
    *,
    session_id: uuid.UUID,
    tenant_id: uuid.UUID,
    elder_id: uuid.UUID,
    now: datetime,
) -> AsrGateEvidence:
    """An ASR Gate row that already accepted this exact transcript."""
    return AsrGateEvidence(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        session_id=session_id,
        elder_id=elder_id,
        language_route="ZH_TW",
        asr_model_version="synthetic-asr-v1",
        confidence=Decimal("0.9700"),
        gate_status="ALLOWED",
        transcript_digest=_digest(SYNTHETIC_TRANSCRIPT),
        expires_at=now + timedelta(minutes=10),
    )


@pytest_asyncio.fixture(loop_scope="function")
async def voice_seed(db_session) -> VoiceSeed:
    now = datetime.now(UTC)
    tenant_id = uuid.uuid4()
    elder_actor_id = uuid.uuid4()
    staff_actor_id = uuid.uuid4()
    elder_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    elder_session_id = uuid.uuid4()
    staff_session_id = uuid.uuid4()

    db_session.add_all(
        [
            Tenant(id=tenant_id, tenant_type="DEMO", name="Synthetic Voice Tenant"),
            Actor(
                id=elder_actor_id,
                actor_type="ELDER",
                display_name="Synthetic Voice Elder Actor",
            ),
            Actor(
                id=staff_actor_id,
                actor_type="HOME_CARE_WORKER",
                display_name="Synthetic Voice Worker Actor",
            ),
            PolicyRegistry(
                id=policy_id,
                policy_code="synthetic-consent-policy",
                policy_type="CONSENT",
                version="v1",
            ),
        ]
    )
    await db_session.flush()

    db_session.add(
        Elder(
            id=elder_id,
            tenant_id=tenant_id,
            actor_id=elder_actor_id,
            display_name="Synthetic Voice Elder",
            primary_care_setting="HOME_CARE",
        )
    )
    await db_session.flush()

    # Grants take effect in the past so a test can expire one without breaking
    # ck_consent_period, which requires expires_at > effective_at.
    granted_at = now - timedelta(hours=1)
    basic_voice = _grant(
        elder_id=elder_id,
        actor_id=elder_actor_id,
        policy_id=policy_id,
        purpose=ConsentPurpose.BASIC_VOICE,
        granted_at=granted_at,
    )
    db_session.add_all(
        [
            basic_voice,
            _grant(
                elder_id=elder_id,
                actor_id=elder_actor_id,
                policy_id=policy_id,
                purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
                granted_at=granted_at,
            ),
            _grant(
                elder_id=elder_id,
                actor_id=elder_actor_id,
                policy_id=policy_id,
                purpose=ConsentPurpose.LONG_TERM_MEMORY,
                granted_at=granted_at,
            ),
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            _voice_session(
                session_id=elder_session_id,
                tenant_id=tenant_id,
                elder_id=elder_id,
                initiator_actor_id=elder_actor_id,
                initiator_type="ELDER",
                consent_id=basic_voice.id,
                trace_id=f"trace-voice-elder-{elder_session_id}",
            ),
            _voice_session(
                session_id=staff_session_id,
                tenant_id=tenant_id,
                elder_id=elder_id,
                initiator_actor_id=staff_actor_id,
                initiator_type="CAREGIVER",
                consent_id=basic_voice.id,
                trace_id=f"trace-voice-staff-{staff_session_id}",
            ),
        ]
    )
    await db_session.flush()

    db_session.add_all(
        [
            _accepted_asr_evidence(
                session_id=elder_session_id,
                tenant_id=tenant_id,
                elder_id=elder_id,
                now=now,
            ),
            _accepted_asr_evidence(
                session_id=staff_session_id,
                tenant_id=tenant_id,
                elder_id=elder_id,
                now=now,
            ),
        ]
    )
    await db_session.flush()

    return VoiceSeed(
        tenant_id=tenant_id,
        elder_id=elder_id,
        elder_actor_id=elder_actor_id,
        staff_actor_id=staff_actor_id,
        elder_session_id=elder_session_id,
        staff_session_id=staff_session_id,
    )


async def _load(db_session, model, entity_id: uuid.UUID):
    result = await db_session.execute(select(model).where(model.id == entity_id))
    return result.scalar_one()


async def _asr_evidence_for(db_session, session_id: uuid.UUID) -> AsrGateEvidence:
    result = await db_session.execute(
        select(AsrGateEvidence).where(AsrGateEvidence.session_id == session_id)
    )
    return result.scalar_one()


def _service(db_session, seed: VoiceSeed) -> CompanionService:
    return CompanionService(db_session, seed.tenant_id, SimpleNamespace(), "mock")


def _elder_context(seed: VoiceSeed) -> ActorContext:
    return ActorContext(
        actor_id=seed.elder_actor_id,
        actor_role="ELDER",
        tenant_id=seed.tenant_id,
    )


@pytest.mark.asyncio
async def test_gated_elder_only_voice_session_unlocks_memory_proposal(
    db_session,
    voice_seed: VoiceSeed,
) -> None:
    """Spec 18 3.4: elder actor, elder-opened session, accepted ASR transcript."""
    service = _service(db_session, voice_seed)
    conversation = await _load(db_session, ConversationSession, voice_seed.elder_session_id)
    asr_evidence = await _asr_evidence_for(db_session, voice_seed.elder_session_id)

    evidence = await service._speaker_evidence(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        turn_reference="turn-1",
        asr_evidence=asr_evidence,
    )
    outputs = await service._requested_outputs(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        speaker_evidence=evidence,
    )

    assert evidence.verification_level == "VERIFIED_ELDER"
    assert evidence.verification_method == "ELDER_ONLY_VOICE_SESSION"
    assert evidence.speaker_actor_id == voice_seed.elder_actor_id
    assert str(asr_evidence.id) in evidence.evidence_reference
    assert outputs == ["event_candidate", "memory_candidate"]


@pytest.mark.asyncio
async def test_staff_initiated_voice_session_withholds_memory_proposal(
    db_session,
    voice_seed: VoiceSeed,
) -> None:
    """Spec 18 6.2: a session someone else opened yields initiator evidence only."""
    service = _service(db_session, voice_seed)
    conversation = await _load(db_session, ConversationSession, voice_seed.staff_session_id)
    asr_evidence = await _asr_evidence_for(db_session, voice_seed.staff_session_id)

    evidence = await service._speaker_evidence(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        turn_reference="turn-1",
        asr_evidence=asr_evidence,
    )
    outputs = await service._requested_outputs(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        speaker_evidence=evidence,
    )

    assert evidence.verification_level == "UNKNOWN"
    assert evidence.verification_method == "UNVERIFIED_VOICE"
    assert evidence.speaker_actor_id is None
    assert outputs == ["event_candidate"]


@pytest.mark.asyncio
async def test_voice_turn_without_asr_gate_evidence_withholds_memory_proposal(
    db_session,
    voice_seed: VoiceSeed,
) -> None:
    """No accepted ASR row means the transcript was never gated by Core."""
    service = _service(db_session, voice_seed)
    conversation = await _load(db_session, ConversationSession, voice_seed.elder_session_id)

    evidence = await service._speaker_evidence(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        turn_reference="turn-1",
        asr_evidence=None,
    )
    outputs = await service._requested_outputs(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        speaker_evidence=evidence,
    )

    assert evidence.verification_level == "UNKNOWN"
    assert outputs == ["event_candidate"]


@pytest.mark.asyncio
async def test_expired_long_term_memory_consent_withholds_memory_proposal(
    db_session,
    voice_seed: VoiceSeed,
) -> None:
    """A verified speaker is not enough; Core re-checks consent every turn."""
    result = await db_session.execute(
        select(ConsentGrant).where(
            ConsentGrant.elder_id == voice_seed.elder_id,
            ConsentGrant.purpose_code == ConsentPurpose.LONG_TERM_MEMORY.value,
        )
    )
    grant = result.scalar_one()
    grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    service = _service(db_session, voice_seed)
    conversation = await _load(db_session, ConversationSession, voice_seed.elder_session_id)
    asr_evidence = await _asr_evidence_for(db_session, voice_seed.elder_session_id)

    evidence = await service._speaker_evidence(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        turn_reference="turn-1",
        asr_evidence=asr_evidence,
    )
    outputs = await service._requested_outputs(
        conversation=conversation,
        actor_context=_elder_context(voice_seed),
        speaker_evidence=evidence,
    )

    assert evidence.verification_level == "VERIFIED_ELDER"
    assert outputs == ["event_candidate"]
