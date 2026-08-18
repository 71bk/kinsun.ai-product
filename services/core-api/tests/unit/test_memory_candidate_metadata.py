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
    memories: list[object] = []
    versions: list[object] = []
    repository = SimpleNamespace(
        add_memory=MagicMock(side_effect=memories.append),
        add_version=MagicMock(side_effect=versions.append),
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
            memory_type="ROUTINE",
            memory_kind="DAILY_ROUTINE",
            normalized_content="每天早餐習慣吃粥。",
            source_event_ids=[event_id],
            confirmation_question="要記住您每天早餐習慣吃粥嗎？",
            extractor_version="memory-extractor-v1",
            extraction_confidence=0.9,
            proposal_risk_hint="MEDIUM",
        ),
        trace_id="trace-memory-metadata",
        idempotency_key="memory-metadata-1",
    )

    assert len(memories) == 1
    memory = memories[0]
    assert memory.memory_kind == "DAILY_ROUTINE"
    assert memory.consent_id == consent_id
    assert len(versions) == 1
    version = versions[0]
    assert version.confirmation_question == "要記住您每天早餐習慣吃粥嗎？"
    assert version.extractor_version == "memory-extractor-v1"
    assert str(version.extraction_confidence) == "0.9000"
    assert len(version.content_digest) == 64
    assert version.source_event_ids == [event_id]
    assert version.proposal_risk_hint == "MEDIUM"
