"""Deterministic server-side ASR gate decisions and confirmation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas.asr_gate import SubmitAsrResultRequest
from app.services.asr_gate_service import AsrGateService


def _service(confidence_threshold: float = 0.85):
    tenant_id = uuid4()
    session = MagicMock()
    session.flush = AsyncMock()
    service = AsrGateService(
        session,
        tenant_id,
        digest_secret="synthetic-asr-gate-secret-at-least-32-bytes",
        confidence_threshold=confidence_threshold,
        evidence_ttl_seconds=900,
    )
    conversation = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        language_route="ZH_TW",
        input_mode="voice_with_text_fallback",
        state="RECORDING",
        consent_id=uuid4(),
        consent_version=1,
    )
    service._conversations = SimpleNamespace(
        get_by_id_for_update=AsyncMock(return_value=conversation)
    )
    service._repo = SimpleNamespace(
        get_for_session_for_update=AsyncMock(return_value=None),
        add=MagicMock(),
    )
    service._conversation_service = SimpleNamespace(transition=AsyncMock())
    service._require_live_voice_consent = AsyncMock()
    service._has_transcript_consent = AsyncMock(return_value=False)
    return service, conversation, session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("confidence", "expected_state", "expected_decision"),
    [
        (0.95, "PROCESSING", "CAN_SEND_TO_AGENT"),
        (0.42, "AWAITING_CONFIRMATION", "CONFIRMATION_REQUIRED"),
    ],
)
async def test_submit_uses_core_threshold_and_never_persists_without_consent(
    confidence: float,
    expected_state: str,
    expected_decision: str,
) -> None:
    service, conversation, _session = _service()
    actor_id = uuid4()
    request = SubmitAsrResultRequest(
        session_id=conversation.id,
        language_route="ZH_TW",
        asr_model_version="synthetic-asr-v1",
        confidence=confidence,
        transcript="synthetic transcript",
    )

    decision = await service.submit(
        request=request,
        actor_id=actor_id,
        correlation_id="correlation-asr",
    )

    assert decision.decision == expected_decision
    transition = service._conversation_service.transition.await_args.kwargs
    assert transition["target_state"] == expected_state
    evidence = service._repo.add.call_args.args[0]
    assert evidence.transcript is None
    assert evidence.transcript_digest != "synthetic transcript"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action", "expected_state", "expected_status", "expected_decision"),
    [
        ("CONFIRM", "PROCESSING", "CONFIRMED", "CAN_SEND_TO_AGENT"),
        ("REJECT", "CANCELLED", "REJECTED", "CANNOT_SEND_TO_AGENT"),
    ],
)
async def test_elder_confirmation_controls_the_formal_session_state(
    action: str,
    expected_state: str,
    expected_status: str,
    expected_decision: str,
) -> None:
    service, conversation, session = _service()
    actor_id = uuid4()
    evidence = SimpleNamespace(
        session_id=conversation.id,
        elder_id=conversation.elder_id,
        gate_status="AWAITING_CONFIRMATION",
        confirmation_action=None,
        confirmed_by_actor_id=None,
        confirmed_at=None,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    service._repo.get_for_session_for_update = AsyncMock(return_value=evidence)
    session.get = AsyncMock(return_value=SimpleNamespace(actor_id=actor_id))

    decision = await service.confirm(
        session_id=conversation.id,
        actor_id=actor_id,
        action=action,
        correlation_id="correlation-confirm",
        idempotency_key="confirm-1",
    )

    assert decision.decision == expected_decision
    assert evidence.gate_status == expected_status
    assert evidence.confirmation_action == action
    assert (
        service._conversation_service.transition.await_args.kwargs["target_state"] == expected_state
    )
