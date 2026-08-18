"""CareEvent persistence boundary for private Memory proposals."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.policies.memory_policy import SourceSpeakerEvidence
from app.schemas.care_event import CreateCareEventCandidateRequest
from app.services import care_event_service
from app.services.care_event_service import CareEventService


def _proposal(memory_kind: str = "DAILY_ROUTINE") -> dict:
    return {
        "memory_type": "ROUTINE",
        "memory_kind": memory_kind,
        "normalized_content": "每天早餐習慣吃粥。",
        "confirmation_question": "要記住您每天早餐習慣吃粥嗎？",
        "extraction_confidence": 0.9,
        "proposal_risk_hint": "MEDIUM",
        "extractor_version": "memory-extractor-v1",
    }


async def _create(
    monkeypatch: pytest.MonkeyPatch,
    *,
    proposal: dict,
    speaker: SourceSpeakerEvidence,
):
    tenant_id = uuid4()
    elder_id = uuid4()
    source_session_id = uuid4()
    versions: list[object] = []
    repository = SimpleNamespace(
        add_event=MagicMock(),
        add_version=MagicMock(side_effect=versions.append),
    )
    session = MagicMock()
    session.flush = AsyncMock()
    monkeypatch.setattr(
        care_event_service,
        "ConsentService",
        MagicMock(
            return_value=SimpleNamespace(
                require_active=AsyncMock(return_value=SimpleNamespace(version=2))
            )
        ),
    )
    monkeypatch.setattr(
        care_event_service,
        "ConversationRepository",
        MagicMock(
            return_value=SimpleNamespace(
                get_for_elder=AsyncMock(return_value=SimpleNamespace(state="COMPLETED"))
            )
        ),
    )
    monkeypatch.setattr(care_event_service, "write_outbox_entry", AsyncMock())
    service = CareEventService(session, tenant_id)
    service._events = repository

    await service.create_candidate(
        elder_id=elder_id,
        actor_id=uuid4(),
        request=CreateCareEventCandidateRequest(
            source_type="CONVERSATION_SESSION",
            source_id=source_session_id,
            event_type="ACTIVITY",
            structured_payload={"activity": "breakfast"},
            confidence_band="HIGH",
            extractor_version="event-extractor-v1",
        ),
        trace_id="trace-care-event-memory-policy",
        idempotency_key="care-event-memory-policy",
        memory_candidate_proposal=proposal,
        source_speaker_evidence=speaker,
    )
    return versions[0]


@pytest.mark.asyncio
async def test_verified_elder_medium_proposal_keeps_bounded_speaker_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = uuid4()
    version = await _create(
        monkeypatch,
        proposal=_proposal(),
        speaker=SourceSpeakerEvidence(
            verification_level="VERIFIED_ELDER",
            evidence_reference="conversation-session:test:authenticated-text",
            speaker_role="ELDER",
            speaker_actor_id=actor_id,
            verification_method="AUTHENTICATED_TEXT",
        ),
    )
    assert version.memory_candidate_proposal == _proposal()
    assert version.speaker_actor_id == actor_id
    assert version.speaker_verification_level == "VERIFIED_ELDER"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("memory_kind", "speaker_level"),
    [
        ("HEALTH_INFERENCE", "VERIFIED_ELDER"),
        ("DAILY_ROUTINE", "THIRD_PARTY"),
        ("DAILY_ROUTINE", "UNKNOWN"),
    ],
)
async def test_high_or_unverified_speaker_proposal_is_discarded_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
    memory_kind: str,
    speaker_level: str,
) -> None:
    version = await _create(
        monkeypatch,
        proposal=_proposal(memory_kind),
        speaker=SourceSpeakerEvidence(
            verification_level=speaker_level,
            evidence_reference=(
                "conversation-session:test:authenticated-text"
                if speaker_level != "UNKNOWN"
                else None
            ),
            speaker_role="FAMILY_MEMBER" if speaker_level == "THIRD_PARTY" else None,
            speaker_actor_id=uuid4() if speaker_level != "UNKNOWN" else None,
            verification_method="AUTHENTICATED_TEXT",
        ),
    )
    assert version.memory_candidate_proposal is None
