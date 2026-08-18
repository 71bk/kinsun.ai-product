"""Fail-closed confirmation authority tests for long-term memory."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationDeniedError, ValidationError
from app.middleware.auth import ActorContext
from app.policies.memory_policy import CURRENT_MEMORY_POLICY_VERSION
from app.policies.memory_retrieval import memory_content_digest
from app.schemas.memory import UpdateMemoryRequest
from app.services.consent_service import ConsentService
from app.services.memory_service import MemoryService


def actor(role: str) -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role=role,
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_voice_confirmation_is_rejected_before_any_repository_access() -> None:
    session = MagicMock()
    service = MemoryService(session, uuid4())

    with pytest.raises(ValidationError) as exc_info:
        await service._validate_confirmation_authority(
            memory=SimpleNamespace(elder_id=uuid4()),
            actor_context=actor("ELDER"),
            request=SimpleNamespace(confirmation_method="VOICE"),
        )

    assert exc_info.value.details[0]["field"] == "confirmation_method"
    session.scalar.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "method"),
    [
        ("DAYCARE_CARE_WORKER", "CAREGIVER_REVIEW"),
        ("HOME_CARE_WORKER", "CAREGIVER_REVIEW"),
        ("FAMILY_MEMBER", "LEGAL_REPRESENTATIVE"),
    ],
)
async def test_non_elder_confirmation_fails_without_repository_access(
    role: str,
    method: str,
) -> None:
    session = MagicMock()
    service = MemoryService(session, uuid4())

    with pytest.raises(AuthorizationDeniedError, match="Resource not found"):
        await service._validate_confirmation_authority(
            memory=SimpleNamespace(elder_id=uuid4()),
            actor_context=actor(role),
            request=SimpleNamespace(confirmation_method=method),
        )

    session.scalar.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_elder_ui_confirmation_activates_with_server_generated_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    service = MemoryService(session, uuid4())
    service._write_event = AsyncMock()
    consent_id = uuid4()
    content = "每天早餐習慣吃粥。"
    digest = memory_content_digest(content)
    service._memories = SimpleNamespace(
        get_current_version=AsyncMock(
            return_value=SimpleNamespace(content=content, content_digest=digest)
        )
    )
    elder = actor("ELDER")
    monkeypatch.setattr(
        "app.services.memory_service.ElderRepository",
        MagicMock(
            return_value=SimpleNamespace(
                get_by_id=AsyncMock(return_value=SimpleNamespace(actor_id=elder.actor_id))
            )
        ),
    )
    memory = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        current_version=2,
        consent_id=consent_id,
        consent_version=3,
        status="PENDING_CONFIRMATION",
        policy_version=CURRENT_MEMORY_POLICY_VERSION,
        actual_risk_level="MEDIUM",
        policy_decision="PENDING_ELDER_CONFIRMATION",
        verification_level="UNVERIFIED",
        required_verification="ELDER_CONFIRMATION",
        lifecycle_reason="ELDER_CONFIRMATION_REQUIRED",
        confirmed_by_actor_id=None,
        confirmed_at=None,
        confirmation_method=None,
        confirmation_session_id=None,
        confirmation_evidence_ref=None,
        confirmed_version=None,
        confirmed_content_digest=None,
        activated_at=None,
    )
    request = SimpleNamespace(
        confirmation_method="ELDER_UI",
        expected_candidate_version=2,
        consent_version=3,
    )

    with patch.object(
        ConsentService,
        "require_active",
        AsyncMock(return_value=SimpleNamespace(id=consent_id, version=3)),
    ):
        result = await service.confirm(
            memory=memory,
            actor_context=elder,
            request=request,
            trace_id="trace-synthetic-elder-confirmation",
            idempotency_key="idem-synthetic-elder-confirmation",
        )

    assert result.status == "ACTIVE"
    assert result.confirmed_by_actor_id == elder.actor_id
    assert result.confirmation_method == "ELDER_UI"
    assert result.confirmation_session_id is None
    assert result.confirmation_evidence_ref == "core-command:trace-synthetic-elder-confirmation"
    assert result.confirmed_version == 2
    assert result.confirmed_content_digest == digest
    assert result.policy_decision == "ELDER_CONFIRMED_MEDIUM"
    assert result.verification_level == "ELDER_CONFIRMED"
    session.flush.assert_awaited_once()
    service._write_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_correction_deactivates_memory_and_clears_stale_trust_evidence() -> None:
    session = MagicMock()
    session.flush = AsyncMock()
    service = MemoryService(session, uuid4())
    service._write_event = AsyncMock()
    versions: list[object] = []
    current = SimpleNamespace(
        memory_version_id=uuid4(),
        version_status="ACTIVE",
        valid_to=None,
        source_event_ids=[uuid4()],
    )
    service._memories = SimpleNamespace(
        get_current_version=AsyncMock(return_value=current),
        add_version=MagicMock(side_effect=versions.append),
    )
    memory = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        current_version=1,
        status="ACTIVE",
        deactivated_at=None,
        actual_risk_level="LOW",
        policy_decision="AUTO_ACTIVATED_LOW",
        policy_version=CURRENT_MEMORY_POLICY_VERSION,
        verification_level="POLICY_VERIFIED",
        required_verification="NONE",
        speaker_verification_level="VERIFIED_ELDER",
        speaker_evidence_reference="speaker-evidence:old",
        confirmed_by_actor_id=None,
        confirmed_at=None,
        confirmation_method=None,
        confirmation_session_id=None,
        confirmation_evidence_ref=None,
        confirmed_version=None,
        confirmed_content_digest=None,
        lifecycle_reason="LOW_ALL_OF_SATISFIED",
    )

    with patch.object(
        ConsentService,
        "require_active",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), version=1)),
    ):
        result = await service.update(
            memory=memory,
            actor_id=uuid4(),
            request=UpdateMemoryRequest(
                content="修改後內容",
                expected_version=1,
                reason_code="CONTENT_CORRECTION",
            ),
            trace_id="trace-memory-correction",
            idempotency_key="idem-memory-correction",
        )

    assert result.status == "INACTIVE"
    assert result.current_version == 2
    assert result.policy_decision == "NO_MEMORY"
    assert result.verification_level == "UNVERIFIED"
    assert result.speaker_verification_level == "UNKNOWN"
    assert result.confirmed_content_digest is None
    assert current.version_status == "INACTIVE"
    assert len(versions) == 1
    assert versions[0].content_digest == memory_content_digest("修改後內容")
