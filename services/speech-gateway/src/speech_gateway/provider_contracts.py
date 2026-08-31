"""Provider-neutral contracts for speech recognition and synthesis.

Only server-owned adapters implement these protocols. Public request models do
not contain provider keys, so a browser cannot redirect Restricted Data to a
different vendor.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from speech_gateway.models import SpeakingSpeed, SpeechLanguage, TranscriptSegment


class ProviderErrorCategory(StrEnum):
    """Bounded provider failures safe to use in logs and HTTP mapping."""

    MISCONFIGURED = "misconfigured"
    AUTHENTICATION = "authentication"
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"


class SpeechProviderError(RuntimeError):
    """A provider failure without upstream payloads, credentials, or content."""

    def __init__(self, provider_key: str, category: ProviderErrorCategory) -> None:
        super().__init__(category.value)
        self.provider_key = provider_key
        self.category = category


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider_key: str
    model_version: str


@dataclass(frozen=True, slots=True)
class AsrProviderRequest:
    audio: bytes
    language: SpeechLanguage
    sample_rate: int


@dataclass(frozen=True, slots=True)
class AsrProviderResult:
    text: str
    confidence: float
    segments: tuple[TranscriptSegment, ...]
    metadata: ProviderMetadata


@dataclass(frozen=True, slots=True)
class TtsProviderRequest:
    text: str
    language: SpeechLanguage
    speaking_speed: SpeakingSpeed


@dataclass(frozen=True, slots=True)
class TtsProviderResult:
    audio: bytes
    content_type: str
    voice_id: str
    metadata: ProviderMetadata


class AsrProvider(Protocol):
    key: str
    supported_languages: frozenset[SpeechLanguage]

    async def transcribe(self, request: AsrProviderRequest) -> AsrProviderResult: ...


class TtsProvider(Protocol):
    key: str
    supported_languages: frozenset[SpeechLanguage]

    async def synthesize(self, request: TtsProviderRequest) -> TtsProviderResult: ...
