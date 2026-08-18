"""Unit tests for the bounded trusted-memory context query."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.policies.memory_retrieval import (
    CURRENT_MEMORY_POLICY_VERSION,
    memory_content_digest,
)
from app.repositories.memory_repo import MemoryRepository


@pytest.mark.asyncio
async def test_candidate_source_evidence_is_current_reviewed_and_tenant_scoped() -> None:
    session = AsyncMock()
    result = MagicMock()
    event_id = uuid4()
    session_id = uuid4()
    result.one_or_none.return_value = (
        event_id,
        2,
        session_id,
        "VERIFIED_ELDER",
        "conversation-session:test:authenticated-text",
        {"memory_kind": "MUSIC_PREFERENCE"},
    )
    session.execute.return_value = result

    evidence = await MemoryRepository(session, uuid4()).get_candidate_source_evidence(
        elder_id=uuid4(),
        source_event_ids=[event_id],
    )

    assert evidence is not None
    assert evidence.source_session_id == session_id
    assert evidence.source_turn_reference == f"care-event:{event_id}:v2"
    assert evidence.speaker_verification_level == "VERIFIED_ELDER"
    assert evidence.memory_candidate_proposal == {"memory_kind": "MUSIC_PREFERENCE"}

    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "care_event.tenant_id" in compiled
    assert "care_event.elder_id" in compiled
    assert "care_event.status" in compiled
    assert "care_event_version.version = eldercare_ai.care_event.current_version" in compiled


@pytest.mark.asyncio
async def test_candidate_source_evidence_rejects_multi_event_bundle_for_now() -> None:
    session = AsyncMock()
    evidence = await MemoryRepository(session, uuid4()).get_candidate_source_evidence(
        elder_id=uuid4(),
        source_event_ids=[uuid4(), uuid4()],
    )
    assert evidence is None
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_context_query_is_tenant_scoped_bounded_and_evidence_gated() -> None:
    session = AsyncMock()
    result = MagicMock()
    memory_id = uuid4()
    consent_id = uuid4()
    content = "喜歡聽歌仔戲"
    result.all.return_value = [
        (
            memory_id,
            3,
            "PREFERENCE",
            content,
            4,
            memory_content_digest(content),
            "MUSIC_PREFERENCE",
            consent_id,
            CURRENT_MEMORY_POLICY_VERSION,
            "AUTO_ACTIVATED_LOW",
            "LOW",
            "POLICY_VERIFIED",
            "NONE",
            "VERIFIED_ELDER",
            "speaker-evidence:test",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
        )
    ]
    session.execute.return_value = result

    disabled_records = await MemoryRepository(session, uuid4()).list_active_context_for_elder(
        elder_id=uuid4(),
        active_consent_id=consent_id,
        active_consent_version=4,
        limit=5,
    )
    records = await MemoryRepository(session, uuid4()).list_active_context_for_elder(
        elder_id=uuid4(),
        active_consent_id=consent_id,
        active_consent_version=4,
        limit=5,
        allow_auto_low_risk_memory=True,
    )

    assert disabled_records == []
    assert records[0].memory_id == memory_id
    assert records[0].version == 3
    assert records[0].content == content
    assert records[0].consent_version == 4

    statement = session.execute.await_args_list[-2].args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "memory.tenant_id" in compiled
    assert "memory.elder_id" in compiled
    assert "memory.status" in compiled
    assert "memory.deleted_at IS NULL" in compiled
    assert "memory.consent_id" in compiled
    assert "memory.consent_version" in compiled
    assert "memory.policy_version" in compiled
    assert "memory_version.version_status" in compiled
    assert "memory_version.valid_from <= now()" in compiled
    assert "memory_version.valid_to IS NULL" in compiled
    assert "char_length(" in compiled
    assert "memory_version.content" in compiled
    assert "graph_projection_record" in compiled
    assert "graph_projection_record.projection_status" in compiled
    assert "memory_confirmation" in compiled
    assert "decision_support_profile_id" in compiled
    assert "EXISTS" in compiled
    assert (
        "graph_projection_record.source_version = eldercare_ai.memory.current_version" in compiled
    )
    assert statement._limit_clause.value == 20


@pytest.mark.asyncio
async def test_active_context_excludes_legacy_row_without_trust_evidence() -> None:
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(uuid4(), 1, "PREFERENCE", "喜歡音樂", 1, *([None] * 16))]
    session.execute.return_value = result

    records = await MemoryRepository(session, uuid4()).list_active_context_for_elder(
        elder_id=uuid4(),
        active_consent_id=uuid4(),
        active_consent_version=1,
        limit=5,
    )

    assert records == []


@pytest.mark.asyncio
async def test_medium_context_requires_matching_append_only_confirmation_record() -> None:
    session = AsyncMock()
    result = MagicMock()
    consent_id = uuid4()
    confirmed_actor_id = uuid4()
    content = "Granddaughter visits every Sunday"
    digest = memory_content_digest(content)

    def medium_row(*, evidence_present: bool) -> tuple[object, ...]:
        return (
            uuid4(),
            2,
            "ROUTINE",
            content,
            3,
            digest,
            "CONTACT_ROUTINE",
            consent_id,
            CURRENT_MEMORY_POLICY_VERSION,
            "ELDER_CONFIRMED_MEDIUM",
            "MEDIUM",
            "ELDER_CONFIRMED",
            "ELDER_CONFIRMATION",
            "VERIFIED_ELDER",
            "speaker-evidence:confirmed-text",
            2,
            digest,
            "ELDER_UI",
            "core-command:confirmation",
            confirmed_actor_id,
            object(),
            None,
            None,
            evidence_present,
        )

    missing_record = medium_row(evidence_present=False)
    matching_record = medium_row(evidence_present=True)
    result.all.return_value = [missing_record, matching_record]
    session.execute.return_value = result

    records = await MemoryRepository(session, uuid4()).list_active_context_for_elder(
        elder_id=uuid4(),
        active_consent_id=consent_id,
        active_consent_version=3,
        limit=5,
    )

    assert [record.memory_id for record in records] == [matching_record[0]]
