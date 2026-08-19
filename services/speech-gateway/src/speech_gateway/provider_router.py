"""Server-owned ASR/TTS provider registry and language router."""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Iterable, Mapping
from typing import cast, get_args

from speech_gateway.models import SpeechLanguage
from speech_gateway.provider_contracts import (
    AsrProvider,
    AsrProviderRequest,
    AsrProviderResult,
    ProviderErrorCategory,
    ProviderMetadata,
    SpeechProviderError,
    TtsProvider,
    TtsProviderRequest,
    TtsProviderResult,
)

SUPPORTED_LANGUAGES = frozenset(cast(tuple[SpeechLanguage, ...], get_args(SpeechLanguage)))
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class ProviderConfigurationError(ValueError):
    """Raised before serving when routing configuration is inconsistent."""


class SpeechProviderRouter:
    def __init__(
        self,
        *,
        asr_providers: Iterable[AsrProvider],
        tts_providers: Iterable[TtsProvider],
        asr_routes: Mapping[SpeechLanguage, str],
        tts_routes: Mapping[SpeechLanguage, str],
        asr_timeout_seconds: float,
        tts_timeout_seconds: float,
    ) -> None:
        self._asr_providers = _build_registry(asr_providers, "ASR")
        self._tts_providers = _build_registry(tts_providers, "TTS")
        self._asr_routes = _validate_routes(asr_routes, self._asr_providers, "ASR")
        self._tts_routes = _validate_routes(tts_routes, self._tts_providers, "TTS")
        self._asr_timeout_seconds = _validate_timeout(asr_timeout_seconds, "ASR")
        self._tts_timeout_seconds = _validate_timeout(tts_timeout_seconds, "TTS")

    async def transcribe(self, request: AsrProviderRequest) -> AsrProviderResult:
        provider_key = self._asr_routes.get(request.language)
        if provider_key is None:
            raise SpeechProviderError("unrouted", ProviderErrorCategory.UNSUPPORTED_LANGUAGE)
        provider = self._asr_providers[provider_key]
        try:
            async with asyncio.timeout(self._asr_timeout_seconds):
                result = await provider.transcribe(request)
        except SpeechProviderError:
            raise
        except TimeoutError as exc:
            raise SpeechProviderError(provider_key, ProviderErrorCategory.TIMEOUT) from exc
        except Exception as exc:
            raise SpeechProviderError(provider_key, ProviderErrorCategory.UNAVAILABLE) from exc
        return _validate_asr_result(result, provider_key)

    async def synthesize(self, request: TtsProviderRequest) -> TtsProviderResult:
        provider_key = self._tts_routes.get(request.language)
        if provider_key is None:
            raise SpeechProviderError("unrouted", ProviderErrorCategory.UNSUPPORTED_LANGUAGE)
        provider = self._tts_providers[provider_key]
        try:
            async with asyncio.timeout(self._tts_timeout_seconds):
                result = await provider.synthesize(request)
        except SpeechProviderError:
            raise
        except TimeoutError as exc:
            raise SpeechProviderError(provider_key, ProviderErrorCategory.TIMEOUT) from exc
        except Exception as exc:
            raise SpeechProviderError(provider_key, ProviderErrorCategory.UNAVAILABLE) from exc
        return _validate_tts_result(result, provider_key)


def _build_registry(providers: Iterable[object], kind: str) -> dict[str, object]:
    registry: dict[str, object] = {}
    for provider in providers:
        key = getattr(provider, "key", "")
        if not isinstance(key, str) or not _SAFE_IDENTIFIER.fullmatch(key):
            raise ProviderConfigurationError(f"{kind} provider has an invalid key")
        if key in registry:
            raise ProviderConfigurationError(f"duplicate {kind} provider key: {key}")
        registry[key] = provider
    return registry


def _validate_routes(
    routes: Mapping[SpeechLanguage, str],
    providers: Mapping[str, object],
    kind: str,
) -> dict[SpeechLanguage, str]:
    missing = SUPPORTED_LANGUAGES.difference(routes)
    extra = set(routes).difference(SUPPORTED_LANGUAGES)
    if missing or extra:
        raise ProviderConfigurationError(f"{kind} routes must cover every supported language")

    validated: dict[SpeechLanguage, str] = {}
    for language, provider_key in routes.items():
        if not _SAFE_IDENTIFIER.fullmatch(provider_key):
            raise ProviderConfigurationError(f"{kind} route has an invalid provider key")
        provider = providers.get(provider_key)
        if provider is None:
            raise ProviderConfigurationError(
                f"unknown {kind} provider '{provider_key}' for {language}"
            )
        supported = getattr(provider, "supported_languages", frozenset())
        if language not in supported:
            raise ProviderConfigurationError(
                f"{kind} provider '{provider_key}' does not support {language}"
            )
        validated[language] = provider_key
    return validated


def _validate_timeout(value: float, kind: str) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ProviderConfigurationError(f"{kind} provider timeout must be positive")
    return value


def _metadata(metadata: ProviderMetadata, expected_key: str) -> ProviderMetadata:
    if metadata.provider_key != expected_key:
        raise SpeechProviderError(expected_key, ProviderErrorCategory.INVALID_RESPONSE)
    model_version = metadata.model_version
    if not isinstance(model_version, str) or not _SAFE_IDENTIFIER.fullmatch(model_version):
        model_version = "unknown"
    return ProviderMetadata(provider_key=expected_key, model_version=model_version)


def _validate_asr_result(result: AsrProviderResult, provider_key: str) -> AsrProviderResult:
    if (
        not isinstance(result.text, str)
        or not isinstance(result.confidence, int | float)
        or not math.isfinite(result.confidence)
        or not 0 <= result.confidence <= 1
    ):
        raise SpeechProviderError(provider_key, ProviderErrorCategory.INVALID_RESPONSE)
    return AsrProviderResult(
        text=result.text,
        confidence=float(result.confidence),
        segments=tuple(result.segments),
        metadata=_metadata(result.metadata, provider_key),
    )


def _validate_tts_result(result: TtsProviderResult, provider_key: str) -> TtsProviderResult:
    if (
        not isinstance(result.audio, bytes)
        or not result.audio
        or not isinstance(result.content_type, str)
        or not result.content_type.startswith("audio/")
        or not isinstance(result.voice_id, str)
        or not result.voice_id
    ):
        raise SpeechProviderError(provider_key, ProviderErrorCategory.INVALID_RESPONSE)
    metadata = _metadata(result.metadata, provider_key)
    voice_id = result.voice_id if _SAFE_IDENTIFIER.fullmatch(result.voice_id) else "unknown"
    return TtsProviderResult(
        audio=result.audio,
        content_type=result.content_type,
        voice_id=voice_id,
        metadata=metadata,
    )
