from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.exceptions import AuthenticationError
from app.schemas.conversation import CompanionTurnResponse
from app.services.speech_synthesis_capability import (
    SpeechSynthesisCapabilityCodec,
    prepare_speech_synthesis_text,
)

SECRET = "synthetic-speech-synthesis-capability-secret-material"
NOW = datetime(2026, 9, 3, 2, 0, tzinfo=UTC)
SESSION_ID = UUID("51000000-0000-4000-8000-000000000001")
AGENT_RUN_ID = UUID("52000000-0000-4000-8000-000000000001")
TENANT_ID = UUID("53000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("54000000-0000-4000-8000-000000000001")
TEXT = "這是受 Core 授權的合成回覆。"


def _verify(codec: SpeechSynthesisCapabilityCodec, value: str, **override: object) -> datetime:
    values = {
        "session_id": SESSION_ID,
        "agent_run_id": AGENT_RUN_ID,
        "tenant_id": TENANT_ID,
        "actor_id": ACTOR_ID,
        "text_sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
        "character_count": len(TEXT),
        "language": "zh-TW",
        "completed_at": NOW,
        **override,
    }
    return codec.verify(value, **values)  # type: ignore[arg-type]


def test_capability_binds_reply_principal_session_and_expiry() -> None:
    codec = SpeechSynthesisCapabilityCodec(SECRET, now=lambda: NOW + timedelta(seconds=1))
    issued = codec.issue(
        session_id=SESSION_ID,
        agent_run_id=AGENT_RUN_ID,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        text=TEXT,
        language="zh-TW",
        completed_at=NOW,
    )

    assert len(issued.value) == 43
    assert issued.expires_at == NOW + timedelta(seconds=60)
    assert _verify(codec, issued.value) == issued.expires_at
    assert codec.digest(issued.value) == hashlib.sha256(issued.value.encode("ascii")).hexdigest()


def test_core_selects_the_exact_bounded_text_authorized_for_tts() -> None:
    reply = "回答內容\r\n\r\n引用來源：\r\n- [官方資料](https://example.test)"

    assert prepare_speech_synthesis_text(reply) == "回答內容"
    assert prepare_speech_synthesis_text(" \n ") is None
    assert prepare_speech_synthesis_text("字" * 3001) is None


@pytest.mark.parametrize(
    "override",
    [
        {"session_id": UUID("51000000-0000-4000-8000-000000000002")},
        {"agent_run_id": UUID("52000000-0000-4000-8000-000000000002")},
        {"tenant_id": UUID("53000000-0000-4000-8000-000000000002")},
        {"actor_id": UUID("54000000-0000-4000-8000-000000000002")},
        {"text_sha256": hashlib.sha256(b"changed").hexdigest()},
        {"character_count": len(TEXT) + 1},
        {"language": "en-US"},
    ],
)
def test_capability_rejects_any_changed_binding(override: dict[str, object]) -> None:
    codec = SpeechSynthesisCapabilityCodec(SECRET, now=lambda: NOW + timedelta(seconds=1))
    issued = codec.issue(
        session_id=SESSION_ID,
        agent_run_id=AGENT_RUN_ID,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        text=TEXT,
        language="zh-TW",
        completed_at=NOW,
    )

    with pytest.raises(AuthenticationError):
        _verify(codec, issued.value, **override)


def test_capability_expires_fail_closed() -> None:
    codec = SpeechSynthesisCapabilityCodec(SECRET, now=lambda: NOW + timedelta(seconds=60))
    issued = codec.issue(
        session_id=SESSION_ID,
        agent_run_id=AGENT_RUN_ID,
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        text=TEXT,
        language="zh-TW",
        completed_at=NOW,
    )

    with pytest.raises(AuthenticationError):
        _verify(codec, issued.value)


@pytest.mark.parametrize("ttl", [14, 121])
def test_capability_configuration_is_bounded(ttl: int) -> None:
    with pytest.raises(ValueError):
        SpeechSynthesisCapabilityCodec(SECRET, ttl_seconds=ttl)


def test_companion_turn_requires_complete_synthesis_transport_fields() -> None:
    base = {
        "session_id": SESSION_ID,
        "agent_run_id": AGENT_RUN_ID,
        "trace_id": "trace-synthesis-transport",
        "context_manifest_id": "context-synthesis-transport",
        "reply_text": TEXT,
        "reply_language": "zh-TW",
        "result_status": "SUCCESS",
        "safety_decision": "ALLOW",
        "risk_level": "LOW",
        "reason_codes": ["ALLOW"],
        "model_route": "synthetic",
    }

    with pytest.raises(ValueError, match="requires all synthesis fields"):
        CompanionTurnResponse(
            **base,
            transport_status="SYNTHESIS_CAPABILITY_ISSUED",
            speech_synthesis_capability="a" * 43,
        )
    with pytest.raises(ValueError, match="text-only"):
        CompanionTurnResponse(
            **base,
            speech_synthesis_text=TEXT,
        )
