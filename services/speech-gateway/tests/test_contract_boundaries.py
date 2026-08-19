"""Boundary tests for the speech gateway.

These use FastAPI's TestClient with the AWS calls patched out: what is asserted
here is the contract shape and the refusals, not Transcribe/Polly behaviour.
The live round trip is verified separately against the real services.
"""

from __future__ import annotations

import base64
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from speech_gateway.app import create_app
from speech_gateway.core_voice_gate import CoreGateDecision, CoreMemoryDecision
from speech_gateway.models import TranscriptSegment
from speech_gateway.settings import get_settings

SESSION_ID = UUID("51000000-0000-4000-8000-000000000001")
VOICE_TICKET = "synthetic-opaque-voice-ticket-material-000000000001"


class FakeCoreGate:
    def __init__(self) -> None:
        self.failed_sessions: list[UUID] = []
        self.memory_decisions: list[dict[str, object]] = []

    async def consume_ticket(self, *, session_id, voice_ticket):  # noqa: ANN001
        assert session_id == SESSION_ID
        assert voice_ticket == VOICE_TICKET

    async def submit_asr_result(self, *, confidence, **kwargs):  # noqa: ANN001, ARG002
        needs_confirmation = confidence < 0.6
        return CoreGateDecision(
            session_id=SESSION_ID,
            decision=("CONFIRMATION_REQUIRED" if needs_confirmation else "CAN_SEND_TO_AGENT"),
            confirmation_required=needs_confirmation,
            expires_at="2026-08-10T12:00:00Z",
        )

    async def fail_session(self, *, session_id):  # noqa: ANN001
        self.failed_sessions.append(session_id)

    async def decide_memory_by_voice(self, **kwargs):  # noqa: ANN003, ANN201
        self.memory_decisions.append(kwargs)
        return CoreMemoryDecision(
            memory_id=kwargs["memory_id"],
            status=("ACTIVE" if kwargs["response_intent"] == "AFFIRM" else "PENDING_CONFIRMATION"),
        )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_transcribe(audio, language, sample_rate, region):  # noqa: ANN001, ARG001
        return (
            "阿嬤您好",
            0.81,
            [TranscriptSegment(text="阿嬤您好", start_time=0.0, end_time=1.0, confidence=0.81)],
        )

    async def fake_synthesize(text, language, speaking_speed, region):  # noqa: ANN001, ARG001
        return b"fake-mp3-bytes", "audio/mpeg", "Zhiyu"

    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", fake_transcribe)
    monkeypatch.setattr("speech_gateway.app.synthesize", fake_synthesize)
    return TestClient(create_app(core_client=FakeCoreGate()))


def _audio(payload: bytes = b"\x00\x01" * 800) -> str:
    return base64.b64encode(payload).decode("ascii")


def _transcription_payload(language: str = "zh-TW") -> dict[str, object]:
    return {
        "audio_base64": _audio(),
        "session_id": str(SESSION_ID),
        "voice_ticket": VOICE_TICKET,
        "language": language,
        "sample_rate": 16000,
    }


def test_transcription_returns_transcript_and_core_gate_decision(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/transcriptions",
        json=_transcription_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "阿嬤您好"
    assert body["gate_decision"] == "CAN_SEND_TO_AGENT"
    assert "confidence" not in body
    assert "voice_ticket" not in body


def test_low_confidence_is_reported_as_not_acceptable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Below the threshold the caller must ask the elder to repeat.

    The gateway still returns the text so the caller can show a confirmation
    prompt, but it must not claim the transcript is usable.
    """

    async def low_confidence(audio, language, sample_rate, region):  # noqa: ANN001, ARG001
        return ("聽不清楚", 0.42, [])

    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", low_confidence)

    response = client.post(
        "/api/v1/speech/transcriptions",
        json=_transcription_payload(),
    )
    assert response.status_code == 200
    assert response.json()["gate_decision"] == "CONFIRMATION_REQUIRED"
    assert response.json()["confirmation_required"] is True


def test_candidate_specific_affirmation_reaches_core_only_after_asr_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def affirmative_transcript(audio, language, sample_rate, region):  # noqa: ANN001, ARG001
        return ("是", 0.96, [])

    core = FakeCoreGate()
    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", affirmative_transcript)
    memory_id = UUID("52000000-0000-4000-8000-000000000002")
    elder_id = UUID("52000000-0000-4000-8000-000000000003")

    response = TestClient(create_app(core_client=core)).post(
        "/api/v1/speech/transcriptions",
        json={
            **_transcription_payload(),
            "memory_confirmation": {
                "elder_id": str(elder_id),
                "memory_id": str(memory_id),
                "confirmation_method": "ELDER_VOICE",
                "expected_candidate_version": 2,
                "consent_version": 3,
                "confirmation_question_digest": "a" * 64,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["memory_decision"] == "ACTIVE"
    assert len(core.memory_decisions) == 1
    assert core.memory_decisions[0]["response_intent"] == "AFFIRM"
    assert core.memory_decisions[0]["memory_id"] == memory_id


def test_low_confidence_memory_answer_has_zero_candidate_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def low_confidence(audio, language, sample_rate, region):  # noqa: ANN001, ARG001
        return ("是", 0.42, [])

    core = FakeCoreGate()
    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", low_confidence)
    response = TestClient(create_app(core_client=core)).post(
        "/api/v1/speech/transcriptions",
        json={
            **_transcription_payload(),
            "memory_confirmation": {
                "elder_id": "52000000-0000-4000-8000-000000000003",
                "memory_id": "52000000-0000-4000-8000-000000000002",
                "confirmation_method": "ELDER_VOICE",
                "expected_candidate_version": 2,
                "consent_version": 3,
                "confirmation_question_digest": "a" * 64,
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["gate_decision"] == "CONFIRMATION_REQUIRED"
    assert response.json()["memory_decision"] is None
    assert core.memory_decisions == []


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_hokkien_and_hakka_without_an_endpoint_are_refused_not_answered_in_mandarin(
    client: TestClient, language: str
) -> None:
    """With no SageMaker endpoint configured these must fail, not fall back.

    Falling through to Transcribe would return a fluent Mandarin transcript of
    words the elder never said. 501 rather than 502 because the request is valid
    and understood — this deployment simply has no model for that language.
    """

    response = client.post(
        "/api/v1/speech/transcriptions",
        json=_transcription_payload(language),
    )
    assert response.status_code == 501


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_hokkien_and_hakka_route_to_sagemaker_when_configured(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """The Mandarin path must not be reachable for these languages."""

    called: dict[str, object] = {}

    async def fake_sagemaker(audio, lang, sample_rate, region, endpoint_name):  # noqa: ANN001, ARG001
        called["language"] = lang
        called["endpoint"] = endpoint_name
        return ("汝食飽未", 0.72, [], "kinsun-asr-v1")

    async def unreachable_transcribe(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("Transcribe must not be used for nan-TW/hak-TW")

    monkeypatch.setenv("SAGEMAKER_ASR_ENDPOINT", "kinsun-speech-asr-v1")
    get_settings.cache_clear()
    monkeypatch.setattr("speech_gateway.app.transcribe_via_sagemaker", fake_sagemaker)
    monkeypatch.setattr("speech_gateway.app.transcribe_pcm", unreachable_transcribe)

    try:
        response = TestClient(create_app(core_client=FakeCoreGate())).post(
            "/api/v1/speech/transcriptions",
            json=_transcription_payload(language),
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "汝食飽未"
    assert body["model_version"] == "kinsun-asr-v1"
    assert called == {"language": language, "endpoint": "kinsun-speech-asr-v1"}


def test_missing_sagemaker_confidence_is_treated_as_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 0.0 score must send the turn to confirmation, not through unchecked."""

    async def zero_confidence(audio, lang, sample_rate, region, endpoint_name):  # noqa: ANN001, ARG001
        return ("汝食飽未", 0.0, [], "kinsun-asr-v1")

    monkeypatch.setenv("SAGEMAKER_ASR_ENDPOINT", "kinsun-speech-asr-v1")
    get_settings.cache_clear()
    monkeypatch.setattr("speech_gateway.app.transcribe_via_sagemaker", zero_confidence)

    try:
        response = TestClient(create_app(core_client=FakeCoreGate())).post(
            "/api/v1/speech/transcriptions",
            json=_transcription_payload("nan-TW"),
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["gate_decision"] == "CONFIRMATION_REQUIRED"


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_hokkien_and_hakka_synthesis_without_endpoint_fails_closed(
    client: TestClient, language: str
) -> None:
    """A missing low-resource endpoint must not fall back to Mandarin Polly."""

    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "汝食飽未", "language": language},
    )
    assert response.status_code == 501


@pytest.mark.parametrize("language", ["nan-TW", "hak-TW"])
def test_hokkien_and_hakka_synthesis_routes_to_sagemaker_when_configured(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    called: dict[str, object] = {}

    async def fake_sagemaker(text, lang, speed, region, endpoint_name):  # noqa: ANN001
        called.update(
            text=text,
            language=lang,
            speed=speed,
            region=region,
            endpoint=endpoint_name,
        )
        return b"RIFFsynthetic-wav", "audio/wav", "synthetic-low-resource-tts-v1"

    async def unreachable_polly(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("Polly must not be used for nan-TW/hak-TW")

    monkeypatch.setenv("SAGEMAKER_TTS_ENDPOINT", "kinsun-speech-tts-v1")
    get_settings.cache_clear()
    monkeypatch.setattr("speech_gateway.app.synthesize_via_sagemaker", fake_sagemaker)
    monkeypatch.setattr("speech_gateway.app.synthesize", unreachable_polly)

    try:
        response = TestClient(create_app(core_client=FakeCoreGate())).post(
            "/api/v1/speech/syntheses",
            json={"text": "synthetic text", "language": language, "speaking_speed": "slow"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert base64.b64decode(response.json()["audio_base64"]) == b"RIFFsynthetic-wav"
    assert response.json()["voice_id"] == "synthetic-low-resource-tts-v1"
    assert called == {
        "text": "synthetic text",
        "language": language,
        "speed": "slow",
        "region": "us-west-2",
        "endpoint": "kinsun-speech-tts-v1",
    }


def test_invalid_base64_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/transcriptions",
        json={**_transcription_payload(), "audio_base64": "!!!not base64!!!"},
    )
    assert response.status_code == 422


def test_empty_audio_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/transcriptions",
        json={**_transcription_payload(), "audio_base64": ""},
    )
    assert response.status_code == 422


def test_validation_error_does_not_echo_audio_or_ticket(client: TestClient) -> None:
    restricted_audio = "restricted-audio-material"
    restricted_ticket = "restricted-ticket-material-000000000000000001"
    response = client.post(
        "/api/v1/speech/transcriptions",
        json={
            "audio_base64": restricted_audio,
            "session_id": str(SESSION_ID),
            "voice_ticket": restricted_ticket,
            "language": "not-a-language",
        },
    )

    assert response.status_code == 422
    assert restricted_audio not in response.text
    assert restricted_ticket not in response.text


def test_unexpected_field_is_refused(client: TestClient) -> None:
    """extra="forbid" keeps the contract able to catch a typo'd field."""

    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "測試", "language": "zh-TW", "speed": "fast"},
    )
    assert response.status_code == 422


def test_browser_cannot_select_or_override_a_provider(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/syntheses",
        json={
            "text": "synthetic text",
            "language": "zh-TW",
            "provider": "browser-selected-provider",
        },
    )
    assert response.status_code == 422
    assert "browser-selected-provider" not in response.text


def test_synthesis_returns_base64_audio(client: TestClient) -> None:
    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "測試", "language": "zh-TW", "speaking_speed": "slow"},
    )
    assert response.status_code == 200
    body = response.json()
    assert base64.b64decode(body["audio_base64"]) == b"fake-mp3-bytes"
    assert body["voice_id"] == "Zhiyu"


def test_upstream_failure_becomes_502_without_leaking_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(text, language, speaking_speed, region):  # noqa: ANN001, ARG001
        raise RuntimeError("bucket=secret-internal-name token=abc123")

    monkeypatch.setattr("speech_gateway.app.synthesize", boom)

    response = client.post(
        "/api/v1/speech/syntheses",
        json={"text": "測試", "language": "zh-TW"},
    )
    assert response.status_code == 502
    assert "secret-internal-name" not in response.text
    assert "abc123" not in response.text
