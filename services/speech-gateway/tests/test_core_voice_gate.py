"""Speech Gateway must fail closed around Core's trusted voice gate."""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from speech_gateway.core_voice_gate import (
    CoreGateRejectedError,
    CoreGateUnavailableError,
    CoreVoiceGateClient,
)

SESSION_ID = UUID("51000000-0000-4000-8000-000000000001")


@pytest.mark.asyncio
async def test_client_consumes_ticket_then_accepts_safe_core_decision() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        assert request.headers["Authorization"] == "Bearer synthetic-service-token"
        if request.url.path.endswith("/voice-tickets/consume"):
            return httpx.Response(
                200,
                json={"data": {"session_id": str(SESSION_ID), "state": "RECORDING"}},
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "session_id": str(SESSION_ID),
                    "decision": "CONFIRMATION_REQUIRED",
                    "confirmation_required": True,
                    "expires_at": "2026-08-10T12:00:00Z",
                }
            },
        )

    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        service_token="synthetic-service-token",
        transport=httpx.MockTransport(handler),
    )

    await client.consume_ticket(
        session_id=SESSION_ID,
        voice_ticket="synthetic-ticket-material-at-least-32-bytes",
    )
    decision = await client.submit_asr_result(
        session_id=SESSION_ID,
        language_route="ZH_TW",
        model_version="synthetic-asr-v1",
        confidence=0.42,
        transcript="synthetic transcript",
    )

    assert decision.decision == "CONFIRMATION_REQUIRED"
    assert seen_paths == [
        "/api/v1/internal/voice-tickets/consume",
        "/api/v1/internal/asr-results",
    ]


@pytest.mark.asyncio
async def test_client_treats_denial_as_non_retryable_gate_rejection() -> None:
    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(lambda _request: httpx.Response(401)),
    )

    with pytest.raises(CoreGateRejectedError):
        await client.consume_ticket(
            session_id=SESSION_ID,
            voice_ticket="synthetic-ticket-material-at-least-32-bytes",
        )


@pytest.mark.asyncio
async def test_public_decision_with_confidence_is_rejected_as_malformed() -> None:
    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "data": {
                        "session_id": str(SESSION_ID),
                        "decision": "CAN_SEND_TO_AGENT",
                        "confirmation_required": False,
                        "expires_at": "2026-08-10T12:00:00Z",
                        "confidence": 0.99,
                    }
                },
            )
        ),
    )

    with pytest.raises(CoreGateUnavailableError):
        await client.submit_asr_result(
            session_id=SESSION_ID,
            language_route="ZH_TW",
            model_version="synthetic-asr-v1",
            confidence=0.99,
            transcript="synthetic transcript",
        )
