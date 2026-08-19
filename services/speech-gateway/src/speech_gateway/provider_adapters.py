"""Adapters around the existing AWS speech implementations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from speech_gateway.models import (
    SageMakerLanguage,
    SpeakingSpeed,
    TranscribeLanguage,
    TranscriptSegment,
)
from speech_gateway.provider_contracts import (
    AsrProviderRequest,
    AsrProviderResult,
    ProviderErrorCategory,
    ProviderMetadata,
    SpeechProviderError,
    TtsProviderRequest,
    TtsProviderResult,
)
from speech_gateway.sagemaker_asr import SageMakerAsrNotConfiguredError
from speech_gateway.sagemaker_tts import SageMakerTtsNotConfiguredError

AwsAsrCallable = Callable[
    [bytes, TranscribeLanguage, int, str],
    Awaitable[tuple[str, float, list[TranscriptSegment]]],
]
SageMakerAsrCallable = Callable[
    [bytes, SageMakerLanguage, int, str, str | None],
    Awaitable[tuple[str, float, list[TranscriptSegment], str]],
]
AwsTtsCallable = Callable[
    [str, TranscribeLanguage, SpeakingSpeed, str],
    Awaitable[tuple[bytes, str, str]],
]
SageMakerTtsCallable = Callable[
    [str, SageMakerLanguage, SpeakingSpeed, str, str | None],
    Awaitable[tuple[bytes, str, str]],
]


class AwsTranscribeAsrProvider:
    key = "aws-transcribe"
    supported_languages = frozenset({"zh-TW", "en-US"})

    def __init__(self, *, region: str, transcribe: AwsAsrCallable, model_version: str) -> None:
        self._region = region
        self._transcribe = transcribe
        self._model_version = model_version

    async def transcribe(self, request: AsrProviderRequest) -> AsrProviderResult:
        text, confidence, segments = await self._transcribe(
            request.audio,
            request.language,  # type: ignore[arg-type]
            request.sample_rate,
            self._region,
        )
        return AsrProviderResult(
            text=text,
            confidence=confidence,
            segments=tuple(segments),
            metadata=ProviderMetadata(self.key, self._model_version),
        )


class SageMakerAsrProvider:
    key = "aws-sagemaker"
    supported_languages = frozenset({"nan-TW", "hak-TW"})

    def __init__(
        self,
        *,
        region: str,
        endpoint_name: str | None,
        transcribe: SageMakerAsrCallable,
    ) -> None:
        self._region = region
        self._endpoint_name = endpoint_name
        self._transcribe = transcribe

    async def transcribe(self, request: AsrProviderRequest) -> AsrProviderResult:
        try:
            text, confidence, segments, model_version = await self._transcribe(
                request.audio,
                request.language,  # type: ignore[arg-type]
                request.sample_rate,
                self._region,
                self._endpoint_name,
            )
        except SageMakerAsrNotConfiguredError as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.MISCONFIGURED) from exc
        return AsrProviderResult(
            text=text,
            confidence=confidence,
            segments=tuple(segments),
            metadata=ProviderMetadata(self.key, model_version),
        )


class AwsPollyTtsProvider:
    key = "aws-polly"
    supported_languages = frozenset({"zh-TW", "en-US"})

    def __init__(self, *, region: str, synthesize: AwsTtsCallable) -> None:
        self._region = region
        self._synthesize = synthesize

    async def synthesize(self, request: TtsProviderRequest) -> TtsProviderResult:
        audio, content_type, voice_id = await self._synthesize(
            request.text,
            request.language,  # type: ignore[arg-type]
            request.speaking_speed,
            self._region,
        )
        return TtsProviderResult(
            audio=audio,
            content_type=content_type,
            voice_id=voice_id,
            metadata=ProviderMetadata(self.key, f"polly-neural:{voice_id}"),
        )


class SageMakerTtsProvider:
    key = "aws-sagemaker"
    supported_languages = frozenset({"nan-TW", "hak-TW"})

    def __init__(
        self,
        *,
        region: str,
        endpoint_name: str | None,
        synthesize: SageMakerTtsCallable,
    ) -> None:
        self._region = region
        self._endpoint_name = endpoint_name
        self._synthesize = synthesize

    async def synthesize(self, request: TtsProviderRequest) -> TtsProviderResult:
        try:
            audio, content_type, model_version = await self._synthesize(
                request.text,
                request.language,  # type: ignore[arg-type]
                request.speaking_speed,
                self._region,
                self._endpoint_name,
            )
        except SageMakerTtsNotConfiguredError as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.MISCONFIGURED) from exc
        return TtsProviderResult(
            audio=audio,
            content_type=content_type,
            voice_id=model_version,
            metadata=ProviderMetadata(self.key, model_version),
        )
