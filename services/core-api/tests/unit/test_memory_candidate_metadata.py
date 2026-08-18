from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.policies.decision_support import (
    DecisionSupportResolution,
    default_standard_resolution,
)
from app.schemas.memory import CreateMemoryCandidateRequest
from app.services import memory_service
from app.services.memory_service import MemoryService


@pytest.mark.asyncio
async def test_create_candidate_persists_confirmation_and_extraction_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    elder_id = uuid4()
    actor_id = uuid4()
    event_id = uuid4()
    consent_id = uuid4()
    source_session_id = uuid4()
    memories: list[object] = []
    versions: list[object] = []
    repository = SimpleNamespace(
        add_memory=MagicMock(side_effect=memories.append),
        add_version=MagicMock(side_effect=versions.append),
        get_candidate_source_evidence=AsyncMock(
            return_value=SimpleNamespace(
                source_session_id=source_session_id,
                source_turn_reference=f"care-event:{event_id}:v1",
                speaker_verification_level="VERIFIED_ELDER",
                speaker_evidence_reference="speaker-evidence:verified-text",
                memory_candidate_proposal={
                    "memory_type": "PREFERENCE",
                    "memory_kind": "MUSIC_PREFERENCE",
                    "normalized_content": "喜歡聽歌仔戲。",
                    "confirmation_question": "要記住您喜歡聽歌仔戲嗎？",
                    "extraction_confidence": 0.9,
                    "proposal_risk_hint": "LOW",
                    "extractor_version": "memory-extractor-v1",
                },
            )
        ),
    )
    session = MagicMock()
    session.scalar = AsyncMock(return_value=1)
    session.flush = AsyncMock()
    monkeypatch.setattr(
        memory_service,
        "MemoryRepository",
        MagicMock(return_value=repository),
    )
    monkeypatch.setattr(
        memory_service,
        "ConsentService",
        MagicMock(
            return_value=SimpleNamespace(
                require_active=AsyncMock(return_value=SimpleNamespace(id=consent_id, version=3))
            )
        ),
    )
    monkeypatch.setattr(memory_service, "write_outbox_entry", AsyncMock())

    service = MemoryService(
        session,
        tenant_id,
        evidence_aware_memory=True,
        auto_low_risk_memory=True,
    )
    service._decision_support_profiles = SimpleNamespace(
        resolve_for_memory=AsyncMock(
            return_value=default_standard_resolution("PREFERENCE")
        )
    )
    await service.create_candidate(
        elder_id=elder_id,
        actor_id=actor_id,
        request=CreateMemoryCandidateRequest(
            memory_type="PREFERENCE",
            memory_kind="MUSIC_PREFERENCE",
            normalized_content="喜歡聽歌仔戲。",
            source_event_ids=[event_id],
            confirmation_question="要記住您喜歡聽歌仔戲嗎？",
            extractor_version="memory-extractor-v1",
            extraction_confidence=0.9,
            proposal_risk_hint="LOW",
        ),
        trace_id="trace-memory-metadata",
        idempotency_key="memory-metadata-1",
    )

    assert len(memories) == 1
    memory = memories[0]
    assert memory.memory_kind == "MUSIC_PREFERENCE"
    assert memory.consent_id == consent_id
    assert memory.status == "ACTIVE"
    assert memory.actual_risk_level == "LOW"
    assert memory.policy_decision == "AUTO_ACTIVATED_LOW"
    assert memory.verification_level == "POLICY_VERIFIED"
    assert memory.speaker_verification_level == "VERIFIED_ELDER"
    assert len(versions) == 1
    version = versions[0]
    assert version.confirmation_question == "要記住您喜歡聽歌仔戲嗎？"
    assert version.extractor_version == "memory-extractor-v1"
    assert str(version.extraction_confidence) == "0.9000"
    assert len(version.content_digest) == 64
    assert version.source_event_ids == [event_id]
    assert version.source_session_id == source_session_id
    assert version.source_turn_reference == f"care-event:{event_id}:v1"
    assert version.proposal_risk_hint == "LOW"


@pytest.mark.asyncio
async def test_create_candidate_fails_before_consent_when_parent_rollout_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_candidate_source_evidence=AsyncMock(),
        add_memory=MagicMock(),
        add_version=MagicMock(),
    )
    require_active = AsyncMock()
    session = MagicMock(flush=AsyncMock())
    monkeypatch.setattr(memory_service, "MemoryRepository", MagicMock(return_value=repository))
    monkeypatch.setattr(
        memory_service,
        "ConsentService",
        MagicMock(return_value=SimpleNamespace(require_active=require_active)),
    )

    service = MemoryService(
        session,
        uuid4(),
        evidence_aware_memory=False,
        auto_low_risk_memory=False,
    )
    service._decision_support_profiles = SimpleNamespace(
        resolve_for_memory=AsyncMock(
            return_value=default_standard_resolution("PREFERENCE")
        )
    )
    with pytest.raises(ValidationError) as exc_info:
        await service.create_candidate(
            elder_id=uuid4(),
            actor_id=uuid4(),
            request=CreateMemoryCandidateRequest(
                memory_type="PREFERENCE",
                memory_kind="MUSIC_PREFERENCE",
                normalized_content="Prefers classical music",
                source_event_ids=[uuid4()],
                confirmation_question="Do you prefer classical music?",
                extractor_version="memory-extractor-v1",
                extraction_confidence=0.9,
                proposal_risk_hint="LOW",
            ),
            trace_id="trace-disabled-memory",
            idempotency_key="disabled-memory-1",
        )

    assert exc_info.value.details[0]["reason"] == "EVIDENCE_AWARE_MEMORY_DISABLED"
    require_active.assert_not_awaited()
    repository.get_candidate_source_evidence.assert_not_awaited()
    repository.add_memory.assert_not_called()
    repository.add_version.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_candidate_fails_before_persistence_when_auto_rollout_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    proposal = {
        "memory_type": "PREFERENCE",
        "memory_kind": "MUSIC_PREFERENCE",
        "normalized_content": "Prefers classical music",
        "confirmation_question": "Do you prefer classical music?",
        "extraction_confidence": 0.9,
        "proposal_risk_hint": "LOW",
        "extractor_version": "memory-extractor-v1",
    }
    repository = SimpleNamespace(
        get_candidate_source_evidence=AsyncMock(
            return_value=SimpleNamespace(
                source_session_id=uuid4(),
                source_turn_reference=f"care-event:{event_id}:v1",
                speaker_verification_level="VERIFIED_ELDER",
                speaker_evidence_reference="speaker-evidence:verified-text",
                memory_candidate_proposal=proposal,
            )
        ),
        add_memory=MagicMock(),
        add_version=MagicMock(),
    )
    session = MagicMock(flush=AsyncMock())
    monkeypatch.setattr(memory_service, "MemoryRepository", MagicMock(return_value=repository))
    monkeypatch.setattr(
        memory_service,
        "ConsentService",
        MagicMock(
            return_value=SimpleNamespace(
                require_active=AsyncMock(return_value=SimpleNamespace(id=uuid4(), version=1))
            )
        ),
    )
    monkeypatch.setattr(memory_service, "write_outbox_entry", AsyncMock())

    service = MemoryService(
        session,
        uuid4(),
        evidence_aware_memory=True,
        auto_low_risk_memory=False,
    )
    service._decision_support_profiles = SimpleNamespace(
        resolve_for_memory=AsyncMock(
            return_value=default_standard_resolution("PREFERENCE")
        )
    )
    with pytest.raises(ValidationError) as exc_info:
        await service.create_candidate(
            elder_id=uuid4(),
            actor_id=uuid4(),
            request=CreateMemoryCandidateRequest(
                memory_type="PREFERENCE",
                memory_kind="MUSIC_PREFERENCE",
                normalized_content="Prefers classical music",
                source_event_ids=[event_id],
                confirmation_question="Do you prefer classical music?",
                extractor_version="memory-extractor-v1",
                extraction_confidence=0.9,
                proposal_risk_hint="LOW",
            ),
            trace_id="trace-auto-low-disabled",
            idempotency_key="auto-low-disabled-1",
        )

    assert exc_info.value.details[0]["reason"] == "AUTO_LOW_RISK_MEMORY_DISABLED"
    repository.add_memory.assert_not_called()
    repository.add_version.assert_not_called()
    session.flush.assert_not_awaited()
    memory_service.write_outbox_entry.assert_not_awaited()


@pytest.mark.asyncio
async def test_supported_profile_routes_low_memory_to_elder_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    profile_id = uuid4()
    proposal = {
        "memory_type": "PREFERENCE",
        "memory_kind": "MUSIC_PREFERENCE",
        "normalized_content": "Prefers classical music",
        "confirmation_question": "Do you want me to remember this music preference?",
        "extraction_confidence": 0.9,
        "proposal_risk_hint": "LOW",
        "extractor_version": "memory-extractor-v1",
    }
    memories: list[object] = []
    repository = SimpleNamespace(
        get_candidate_source_evidence=AsyncMock(
            return_value=SimpleNamespace(
                source_session_id=uuid4(),
                source_turn_reference=f"care-event:{event_id}:v1",
                speaker_verification_level="VERIFIED_ELDER",
                speaker_evidence_reference="speaker-evidence:verified-text",
                memory_candidate_proposal=proposal,
            )
        ),
        add_memory=MagicMock(side_effect=memories.append),
        add_version=MagicMock(),
    )
    session = MagicMock(flush=AsyncMock())
    monkeypatch.setattr(memory_service, "MemoryRepository", MagicMock(return_value=repository))
    monkeypatch.setattr(
        memory_service,
        "ConsentService",
        MagicMock(
            return_value=SimpleNamespace(
                require_active=AsyncMock(return_value=SimpleNamespace(id=uuid4(), version=2))
            )
        ),
    )
    monkeypatch.setattr(memory_service, "write_outbox_entry", AsyncMock())
    service = MemoryService(
        session,
        uuid4(),
        evidence_aware_memory=True,
        auto_low_risk_memory=False,
    )
    service._decision_support_profiles = SimpleNamespace(
        resolve_for_memory=AsyncMock(
            return_value=DecisionSupportResolution(
                usable=True,
                mode="SUPPORTED",
                allowed_memory_risks=frozenset({"LOW", "MEDIUM"}),
                profile_id=profile_id,
                profile_version=3,
                data_class="PREFERENCE",
                reason_code="DECISION_SUPPORT_PROFILE_ACTIVE",
            )
        )
    )

    result = await service.create_candidate(
        elder_id=uuid4(),
        actor_id=uuid4(),
        request=CreateMemoryCandidateRequest(**proposal, source_event_ids=[event_id]),
        trace_id="trace-supported-low",
        idempotency_key="supported-low-1",
    )

    assert result.status == "PENDING_CONFIRMATION"
    assert result.actual_risk_level == "LOW"
    assert result.policy_decision == "PENDING_SUPPORTED_CONFIRMATION"
    assert result.required_verification == "SUPPORTED_ELDER_CONFIRMATION"
    assert result.decision_support_profile_id == profile_id
    assert result.decision_support_profile_version == 3
    assert len(memories) == 1


@pytest.mark.asyncio
async def test_representative_required_profile_creates_no_elder_owned_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = uuid4()
    proposal = {
        "memory_type": "PREFERENCE",
        "memory_kind": "MUSIC_PREFERENCE",
        "normalized_content": "Prefers classical music",
        "confirmation_question": "Do you want me to remember this music preference?",
        "extraction_confidence": 0.9,
        "proposal_risk_hint": "LOW",
        "extractor_version": "memory-extractor-v1",
    }
    repository = SimpleNamespace(
        get_candidate_source_evidence=AsyncMock(
            return_value=SimpleNamespace(
                source_session_id=uuid4(),
                source_turn_reference=f"care-event:{event_id}:v1",
                speaker_verification_level="VERIFIED_ELDER",
                speaker_evidence_reference="speaker-evidence:verified-text",
                memory_candidate_proposal=proposal,
            )
        ),
        add_memory=MagicMock(),
        add_version=MagicMock(),
    )
    session = MagicMock(flush=AsyncMock())
    monkeypatch.setattr(memory_service, "MemoryRepository", MagicMock(return_value=repository))
    monkeypatch.setattr(
        memory_service,
        "ConsentService",
        MagicMock(
            return_value=SimpleNamespace(
                require_active=AsyncMock(return_value=SimpleNamespace(id=uuid4(), version=2))
            )
        ),
    )
    service = MemoryService(
        session,
        uuid4(),
        evidence_aware_memory=True,
        auto_low_risk_memory=True,
    )
    service._decision_support_profiles = SimpleNamespace(
        resolve_for_memory=AsyncMock(
            return_value=DecisionSupportResolution(
                usable=True,
                mode="REPRESENTATIVE_REQUIRED",
                allowed_memory_risks=frozenset(),
                profile_id=uuid4(),
                profile_version=1,
                data_class="PREFERENCE",
                reason_code="DECISION_SUPPORT_PROFILE_ACTIVE",
            )
        )
    )

    with pytest.raises(ValidationError) as exc_info:
        await service.create_candidate(
            elder_id=uuid4(),
            actor_id=uuid4(),
            request=CreateMemoryCandidateRequest(**proposal, source_event_ids=[event_id]),
            trace_id="trace-representative-required",
            idempotency_key="representative-required-1",
        )

    assert exc_info.value.details[0]["reason"] == (
        "REPRESENTATIVE_REQUIRED_NO_ELDER_MEMORY"
    )
    repository.add_memory.assert_not_called()
    repository.add_version.assert_not_called()
    session.flush.assert_not_awaited()
