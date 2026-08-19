"""Provider routing tests use deterministic adapters and synthetic content only."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from speech_gateway.models import SpeechLanguage
from speech_gateway.provider_contracts import (
    AsrProviderRequest,
    AsrProviderResult,
    ProviderErrorCategory,
    ProviderMetadata,
    SpeechProviderError,
    TtsProviderRequest,
    TtsProviderResult,
)
from speech_gateway.provider_router import ProviderConfigurationError, SpeechProviderRouter

ALL_LANGUAGES: frozenset[SpeechLanguage] = frozenset({"zh-TW", "en-US", "nan-TW", "hak-TW"})


class DeterministicAsrProvider:
    """Test-only adapter; never registered by the runtime application."""

    def __init__(
        self,
        key: str,
        *,
        supported_languages: frozenset[SpeechLanguage] = ALL_LANGUAGES,
        delay_seconds: float = 0,
        error: Exception | None = None,
        model_version: str = "synthetic-asr-v1",
    ) -> None:
        self.key = key
        self.supported_languages = supported_languages
        self.delay_seconds = delay_seconds
        self.error = error
        self.model_version = model_version
        self.calls: list[SpeechLanguage] = []

    async def transcribe(self, request: AsrProviderRequest) -> AsrProviderResult:
        self.calls.append(request.language)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error:
            raise self.error
        return AsrProviderResult(
            text="synthetic transcript",
            confidence=0.9,
            segments=(),
            metadata=ProviderMetadata(self.key, self.model_version),
        )


class DeterministicTtsProvider:
    """Test-only adapter; never registered by the runtime application."""

    def __init__(
        self,
        key: str,
        *,
        supported_languages: frozenset[SpeechLanguage] = ALL_LANGUAGES,
        error: Exception | None = None,
    ) -> None:
        self.key = key
        self.supported_languages = supported_languages
        self.error = error
        self.calls: list[SpeechLanguage] = []

    async def synthesize(self, request: TtsProviderRequest) -> TtsProviderResult:
        self.calls.append(request.language)
        if self.error:
            raise self.error
        return TtsProviderResult(
            audio=b"synthetic-audio",
            content_type="audio/mpeg",
            voice_id="synthetic-voice",
            metadata=ProviderMetadata(self.key, "synthetic-tts-v1"),
        )


def _router(
    *,
    primary_asr: DeterministicAsrProvider,
    secondary_asr: DeterministicAsrProvider | None = None,
    asr_routes: dict[SpeechLanguage, str] | None = None,
) -> SpeechProviderRouter:
    tts = DeterministicTtsProvider("test-tts")
    return SpeechProviderRouter(
        asr_providers=(primary_asr,) if secondary_asr is None else (primary_asr, secondary_asr),
        tts_providers=(tts,),
        asr_routes=asr_routes or {language: primary_asr.key for language in ALL_LANGUAGES},
        tts_routes={language: tts.key for language in ALL_LANGUAGES},
        asr_timeout_seconds=0.01,
        tts_timeout_seconds=0.01,
    )


def _asr_request(language: SpeechLanguage) -> AsrProviderRequest:
    return AsrProviderRequest(audio=b"synthetic-pcm", language=language, sample_rate=16000)


@pytest.mark.asyncio
async def test_each_language_routes_to_its_server_configured_asr_provider() -> None:
    managed = DeterministicAsrProvider("test-managed")
    private = DeterministicAsrProvider("test-private")
    router = _router(
        primary_asr=managed,
        secondary_asr=private,
        asr_routes={
            "zh-TW": "test-managed",
            "en-US": "test-managed",
            "nan-TW": "test-private",
            "hak-TW": "test-private",
        },
    )

    for language in ("zh-TW", "en-US", "nan-TW", "hak-TW"):
        result = await router.transcribe(_asr_request(language))
        expected = "test-private" if language in {"nan-TW", "hak-TW"} else "test-managed"
        assert result.metadata.provider_key == expected

    assert managed.calls == ["zh-TW", "en-US"]
    assert private.calls == ["nan-TW", "hak-TW"]


def test_unknown_provider_key_fails_during_router_construction() -> None:
    provider = DeterministicAsrProvider("test-asr")
    routes = {language: provider.key for language in ALL_LANGUAGES}
    routes["zh-TW"] = "not-registered"

    with pytest.raises(ProviderConfigurationError, match="unknown ASR provider"):
        _router(primary_asr=provider, asr_routes=routes)


def test_provider_language_mismatch_fails_during_router_construction() -> None:
    provider = DeterministicAsrProvider(
        "test-asr",
        supported_languages=frozenset({"zh-TW"}),
    )

    with pytest.raises(ProviderConfigurationError, match="does not support"):
        _router(primary_asr=provider)


@pytest.mark.asyncio
async def test_timeout_fails_closed_without_calling_another_provider() -> None:
    slow = DeterministicAsrProvider("test-slow", delay_seconds=0.05)
    fallback = DeterministicAsrProvider("test-fallback")
    router = _router(primary_asr=slow, secondary_asr=fallback)

    with pytest.raises(SpeechProviderError) as caught:
        await router.transcribe(_asr_request("zh-TW"))

    assert caught.value.category == ProviderErrorCategory.TIMEOUT
    assert slow.calls == ["zh-TW"]
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_misconfiguration_category_is_preserved_without_fallback() -> None:
    configured_error = SpeechProviderError(
        "test-primary",
        ProviderErrorCategory.MISCONFIGURED,
    )
    primary = DeterministicAsrProvider("test-primary", error=configured_error)
    fallback = DeterministicAsrProvider("test-fallback")
    router = _router(primary_asr=primary, secondary_asr=fallback)

    with pytest.raises(SpeechProviderError) as caught:
        await router.transcribe(_asr_request("nan-TW"))

    assert caught.value.category == ProviderErrorCategory.MISCONFIGURED
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_unbounded_upstream_exception_becomes_bounded_unavailable_error() -> None:
    provider = DeterministicAsrProvider(
        "test-asr",
        error=RuntimeError("credential=restricted-upstream-detail"),
    )
    router = _router(primary_asr=provider)

    with pytest.raises(SpeechProviderError) as caught:
        await router.transcribe(_asr_request("en-US"))

    assert caught.value.category == ProviderErrorCategory.UNAVAILABLE
    assert "restricted-upstream-detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_unsupported_language_fails_closed_inside_the_router() -> None:
    provider = DeterministicAsrProvider("test-asr")
    router = _router(primary_asr=provider)
    unsupported = cast(SpeechLanguage, "fr-FR")

    with pytest.raises(SpeechProviderError) as caught:
        await router.transcribe(_asr_request(unsupported))

    assert caught.value.category == ProviderErrorCategory.UNSUPPORTED_LANGUAGE
    assert provider.calls == []


@pytest.mark.asyncio
async def test_model_metadata_is_bounded_before_audit_or_core_submission() -> None:
    provider = DeterministicAsrProvider(
        "test-asr",
        model_version="token=restricted metadata with spaces",
    )
    router = _router(primary_asr=provider)

    result = await router.transcribe(_asr_request("zh-TW"))

    assert result.metadata == ProviderMetadata("test-asr", "unknown")


@pytest.mark.asyncio
async def test_tts_uses_the_independent_server_side_route() -> None:
    asr = DeterministicAsrProvider("test-asr")
    tts = DeterministicTtsProvider("test-tts")
    router = SpeechProviderRouter(
        asr_providers=(asr,),
        tts_providers=(tts,),
        asr_routes={language: asr.key for language in ALL_LANGUAGES},
        tts_routes={language: tts.key for language in ALL_LANGUAGES},
        asr_timeout_seconds=1,
        tts_timeout_seconds=1,
    )

    result = await router.synthesize(
        TtsProviderRequest(text="synthetic", language="hak-TW", speaking_speed="normal")
    )

    assert result.metadata.provider_key == "test-tts"
    assert tts.calls == ["hak-TW"]


@pytest.mark.asyncio
async def test_tts_failure_does_not_call_another_registered_provider() -> None:
    asr = DeterministicAsrProvider("test-asr")
    provider_error = SpeechProviderError("test-primary-tts", ProviderErrorCategory.UNAVAILABLE)
    primary = DeterministicTtsProvider("test-primary-tts", error=provider_error)
    fallback = DeterministicTtsProvider("test-fallback-tts")
    router = SpeechProviderRouter(
        asr_providers=(asr,),
        tts_providers=(primary, fallback),
        asr_routes={language: asr.key for language in ALL_LANGUAGES},
        tts_routes={language: primary.key for language in ALL_LANGUAGES},
        asr_timeout_seconds=1,
        tts_timeout_seconds=1,
    )

    with pytest.raises(SpeechProviderError) as caught:
        await router.synthesize(
            TtsProviderRequest(text="synthetic", language="zh-TW", speaking_speed="normal")
        )

    assert caught.value.category == ProviderErrorCategory.UNAVAILABLE
    assert primary.calls == ["zh-TW"]
    assert fallback.calls == []
