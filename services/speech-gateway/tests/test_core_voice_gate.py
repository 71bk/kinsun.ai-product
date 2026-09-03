"""Speech Gateway must fail closed around Core's trusted voice gate."""

from __future__ import annotations

import json
from uuid import UUID

import httpx
import pytest

from speech_gateway.core_voice_gate import (
    CoreGateRejectedError,
    CoreGateUnavailableError,
    CoreSynthesisRateLimitedError,
    CoreVoiceGateClient,
)
from speech_gateway.service_identity import ServiceCredentialSigner

SESSION_ID = UUID("51000000-0000-4000-8000-000000000001")
SERVICE_SECRET = "synthetic-service-identity-secret-material-32-bytes"
AGENT_RUN_ID = UUID("52000000-0000-4000-8000-000000000001")
TENANT_ID = UUID("53000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("54000000-0000-4000-8000-000000000001")


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
        assert json.loads(request.content)["confidence"] == 0.8765
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
        confidence=0.876543,
        transcript="synthetic transcript",
    )

    assert decision.decision == "CONFIRMATION_REQUIRED"
    assert seen_paths == [
        "/api/v1/internal/voice-tickets/consume",
        "/api/v1/internal/asr-results",
    ]


@pytest.mark.asyncio
async def test_client_signs_each_core_request_and_propagates_correlation() -> None:
    seen_credentials: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        credential = request.headers["X-Kinsun-Service-Credential"]
        assert credential.startswith("ksvc1.")
        assert request.headers["X-Correlation-ID"]
        assert "Authorization" not in request.headers
        seen_credentials.append(credential)
        return httpx.Response(
            200,
            json={"data": {"session_id": str(SESSION_ID), "state": "RECORDING"}},
        )

    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        service_signer=ServiceCredentialSigner(secret=SERVICE_SECRET),
        transport=httpx.MockTransport(handler),
    )

    await client.consume_ticket(
        session_id=SESSION_ID,
        voice_ticket="synthetic-ticket-material-at-least-32-bytes",
    )
    await client.consume_ticket(
        session_id=SESSION_ID,
        voice_ticket="synthetic-ticket-material-at-least-32-bytes",
    )

    assert len(seen_credentials) == 2
    assert seen_credentials[0] != seen_credentials[1]


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
async def test_client_consumes_synthesis_capability_and_validates_principal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/internal/speech-synthesis-capabilities/consume"
        payload = json.loads(request.content)
        assert payload["capability"] == "synthetic-capability-material-at-least-32-bytes"
        assert payload["text_sha256"] == "a" * 64
        assert payload["client_ip_hash"] == "b" * 64
        return httpx.Response(
            200,
            json={
                "data": {
                    "session_id": str(SESSION_ID),
                    "agent_run_id": str(AGENT_RUN_ID),
                    "tenant_id": str(TENANT_ID),
                    "actor_id": str(ACTOR_ID),
                }
            },
        )

    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        service_token="synthetic-service-token",
        transport=httpx.MockTransport(handler),
    )

    principal = await client.consume_synthesis_capability(
        session_id=SESSION_ID,
        agent_run_id=AGENT_RUN_ID,
        capability="synthetic-capability-material-at-least-32-bytes",
        text_sha256="a" * 64,
        character_count=12,
        language="zh-TW",
        client_ip_hash="b" * 64,
    )

    assert principal.tenant_id == TENANT_ID
    assert principal.actor_id == ACTOR_ID


@pytest.mark.asyncio
async def test_client_surfaces_core_synthesis_retry_after() -> None:
    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(429, headers={"Retry-After": "23"})
        ),
    )

    with pytest.raises(CoreSynthesisRateLimitedError) as caught:
        await client.consume_synthesis_capability(
            session_id=SESSION_ID,
            agent_run_id=AGENT_RUN_ID,
            capability="synthetic-capability-material-at-least-32-bytes",
            text_sha256="a" * 64,
            character_count=12,
            language="zh-TW",
            client_ip_hash="b" * 64,
        )

    assert caught.value.retry_after_seconds == 23


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


@pytest.mark.asyncio
async def test_client_submits_bounded_candidate_specific_memory_decision() -> None:
    memory_id = UUID("52000000-0000-4000-8000-000000000002")
    elder_id = UUID("52000000-0000-4000-8000-000000000003")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == (
            f"/api/v1/internal/elders/{elder_id}/memory-candidates/{memory_id}/voice-confirmation"
        )
        assert request.headers["Idempotency-Key"].startswith("memory-voice:")
        payload = json.loads(request.content)
        assert payload["response_intent"] == "AFFIRM"
        assert "transcript" not in payload
        return httpx.Response(
            200,
            json={"data": {"memory_id": str(memory_id), "status": "ACTIVE"}},
        )

    client = CoreVoiceGateClient(
        base_url="http://core.test",
        timeout_seconds=1,
        service_token="synthetic-service-token",
        transport=httpx.MockTransport(handler),
    )
    result = await client.decide_memory_by_voice(
        elder_id=elder_id,
        memory_id=memory_id,
        session_id=SESSION_ID,
        confirmation_method="ELDER_VOICE",
        expected_candidate_version=2,
        consent_version=3,
        confirmation_question_digest="a" * 64,
        response_intent="AFFIRM",
        witness_actor_id=None,
        witness_evidence_reference=None,
    )

    assert result.status == "ACTIVE"
