from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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


class SynthesizeRequest(GatewayModel):
    text: str = Field(min_length=1, max_length=3000)
    # Mandarin/English use Polly; Hokkien/Hakka require the private SageMaker
    # endpoint and fail closed when it has not been configured.
    language: SpeechLanguage
    speaking_speed: SpeakingSpeed = "normal"


class SynthesizeResponse(GatewayModel):
    audio_base64: str
    content_type: str
    voice_id: str
