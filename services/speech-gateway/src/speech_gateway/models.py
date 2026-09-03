from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Mandarin and English go to Amazon Transcribe.
TranscribeLanguage = Literal["zh-TW", "en-US"]

# Hokkien and Hakka go to a self-hosted SageMaker endpoint. Sending them to a
# Mandarin model instead would transcribe Taiwanese speech with the wrong model
# and report the result as if it had been understood.
SageMakerLanguage = Literal["nan-TW", "hak-TW"]

SpeechLanguage = Literal["zh-TW", "en-US", "nan-TW", "hak-TW"]
SpeakingSpeed = Literal["slow", "normal", "fast"]


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MemoryVoiceConfirmationContext(GatewayModel):
    elder_id: UUID
    memory_id: UUID
    confirmation_method: Literal["ELDER_VOICE", "WITNESSED_VOICE"]
    expected_candidate_version: int = Field(ge=1)
    consent_version: int = Field(ge=1)
    confirmation_question_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    witness_actor_id: UUID | None = None
    witness_evidence_reference: str | None = Field(
        default=None,
        pattern=r"^evidence:[0-9a-fA-F-]{36}$",
        max_length=300,
    )

    @model_validator(mode="after")
    def validate_witness_pair(self) -> MemoryVoiceConfirmationContext:
        witnessed = self.confirmation_method == "WITNESSED_VOICE"
        paired = self.witness_actor_id is not None and self.witness_evidence_reference is not None
        if witnessed != paired:
            raise ValueError("witness identity and evidence must match WITNESSED_VOICE")
        return self


class TranscribeRequest(GatewayModel):
    """Audio is base64 so the boundary stays a plain JSON contract."""

    audio_base64: str = Field(min_length=1)
    session_id: UUID
    voice_ticket: str = Field(min_length=32, max_length=128)
    language: SpeechLanguage
    # 16 kHz mono PCM is what the browser recorder produces and what Transcribe
    # expects; the field is explicit because a mismatch yields silent garbage
    # rather than an error.
    sample_rate: int = Field(default=16000, ge=8000, le=48000)
    encoding: Literal["pcm"] = "pcm"
    memory_confirmation: MemoryVoiceConfirmationContext | None = None


class TranscriptSegment(GatewayModel):
    text: str
    start_time: float
    end_time: float
    confidence: float


class TranscribeResponse(GatewayModel):
    session_id: UUID
    text: str
    language: SpeechLanguage
    model_version: str
    gate_decision: Literal[
        "CAN_SEND_TO_AGENT",
        "CONFIRMATION_REQUIRED",
        "CANNOT_SEND_TO_AGENT",
    ]
    confirmation_required: bool
    gate_expires_at: datetime
    memory_decision: (
        Literal[
            "ACTIVE",
            "REJECTED",
            "DEFERRED",
            "PENDING_CONFIRMATION",
        ]
        | None
    ) = None


class SynthesizeRequest(GatewayModel):
    text: str = Field(min_length=1, max_length=3000)
    session_id: UUID
    agent_run_id: UUID
    # Mandarin/English use a server-routed managed provider; Hokkien/Hakka
    # require the private SageMaker endpoint and fail closed when unavailable.
    language: SpeechLanguage
    speaking_speed: SpeakingSpeed = "normal"


class SynthesizeResponse(GatewayModel):
    audio_base64: str
    content_type: str
    voice_id: str
