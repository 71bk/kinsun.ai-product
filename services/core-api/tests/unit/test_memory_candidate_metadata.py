from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

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

    await MemoryService(session, tenant_id).create_candidate(
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
