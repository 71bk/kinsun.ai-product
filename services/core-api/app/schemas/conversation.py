"""Conversation-session API schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LanguageRoute(str, Enum):
    ZH_TW = "ZH_TW"
    NAN_TW = "NAN_TW"
    HAK_TW = "HAK_TW"
    EN_US = "EN_US"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class CreateVoiceSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language_preference: LanguageRoute
    input_mode: Literal["voice", "text", "voice_with_text_fallback"]
    client_audio_format: str | None = Field(default=None, max_length=80)
    client_timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)
    purpose: Literal["BASIC_VOICE"] = "BASIC_VOICE"


class TransitionVoiceSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_state: Literal[
        "RECORDING",
        "PROCESSING",
        "RESPONDING",
        "COMPLETED",
        "CANCELLED",
        "FAILED",
    ]


class VoiceSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: UUID
    elder_id: UUID
    state: Literal[
        "CREATED",
        "RECORDING",
        "PROCESSING",
        "RESPONDING",
        "COMPLETED",
        "CANCELLED",
        "FAILED",
    ]
    language_route: LanguageRoute
    consent_version: int
    policy_version: str | None
    started_at: datetime
    ended_at: datetime | None
    transport_status: Literal["NOT_CONFIGURED", "AVAILABLE"] = "NOT_CONFIGURED"
    websocket_url: str | None = None
    connection_token: str | None = None
