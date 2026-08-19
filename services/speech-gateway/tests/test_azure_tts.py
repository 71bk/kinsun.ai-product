"""Azure TTS adapter tests use synthetic text and in-memory HTTP only."""

from __future__ import annotations

from typing import cast

import httpx
import pytest

from speech_gateway.app import _build_provider_router
from speech_gateway.azure_tts import AzureSpeechTtsProvider
from speech_gateway.models import SpeakingSpeed, SpeechLanguage
from speech_gateway.provider_contracts import (
    ProviderErrorCategory,
    SpeechProviderError,
    TtsProviderRequest,
)
from speech_gateway.provider_router import ProviderConfigurationError
from speech_gateway.settings import Settings

SYNTHETIC_MP3 = b"synthetic-mp3-audio"


def _request(
    language: SpeechLanguage = "zh-TW",
    speed: SpeakingSpeed = "normal",
) -> TtsProviderRequest:
    return TtsProviderRequest(
        text='care & <safe> "quoted"',
        language=language,
        speaking_speed=speed,
    )


def _provider(
    handler,
    *,
    key: str = "synthetic-azure-key",
    region: str = "eastus",
    voice_zh_tw: str = "zh-TW-HsiaoChenNeural",
    voice_en_us: str = "en-US-JennyNeural",
) -> AzureSpeechTtsProvider:
    return AzureSpeechTtsProvider(
        subscription_key=key,
        region=region,
        voice_zh_tw=voice_zh_tw,
        voice_en_us=voice_en_us,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "speed", "voice", "rate"),
    [
        ("zh-TW", "slow", "zh-TW-HsiaoChenNeural", "-20%"),
        ("zh-TW", "normal", "zh-TW-HsiaoChenNeural", "0%"),
        ("en-US", "fast", "en-US-JennyNeural", "+20%"),
    ],
)
async def test_request_policy_is_server_owned_and_response_is_normalized(
    language: SpeechLanguage,
    speed: SpeakingSpeed,
    voice: str,
    rate: str,
) -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            content=SYNTHETIC_MP3,
            headers={"Content-Type": "audio/mpeg"},
        )

    result = await _provider(handler).synthesize(_request(language, speed))

    assert len(captured) == 1
    upstream = captured[0]
    assert str(upstream.url) == "https://eastus.tts.speech.microsoft.com/cognitiveservices/v1"
    assert upstream.method == "POST"
    assert upstream.headers["ocp-apim-subscription-key"] == "synthetic-azure-key"
    assert upstream.headers["content-type"] == "application/ssml+xml"
    assert upstream.headers["x-microsoft-outputformat"] == ("audio-24khz-48kbitrate-mono-mp3")
    assert upstream.headers["user-agent"] == "kinsun-speech-gateway"

    ssml = upstream.content.decode("utf-8")
    assert f'xml:lang="{language}"' in ssml
    assert f'name="{voice}"' in ssml
    assert f'rate="{rate}"' in ssml
    assert "care &amp; &lt;safe&gt;" in ssml
    assert "care & <safe>" not in ssml

    assert result.audio == SYNTHETIC_MP3
    assert result.content_type == "audio/mpeg"
    assert result.voice_id == voice
    assert result.metadata.provider_key == "azure-speech-tts"
    assert result.metadata.model_version == f"azure-speech:{voice}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "region", "voice_zh_tw"),
    [
        ("", "eastus", "zh-TW-HsiaoChenNeural"),
        ("synthetic-azure-key", "", "zh-TW-HsiaoChenNeural"),
        ("synthetic-azure-key", "eastus", "invalid voice with spaces"),
    ],
)
async def test_missing_or_invalid_server_configuration_fails_before_http(
    key: str,
    region: str,
    voice_zh_tw: str,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=SYNTHETIC_MP3)

    provider = _provider(handler, key=key, region=region, voice_zh_tw=voice_zh_tw)

    with pytest.raises(SpeechProviderError) as caught:
        await provider.synthesize(_request())

    assert caught.value.category == ProviderErrorCategory.MISCONFIGURED
    assert calls == 0


@pytest.mark.asyncio
async def test_low_resource_language_is_refused_before_http() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=SYNTHETIC_MP3)

    provider = _provider(handler)

    with pytest.raises(SpeechProviderError) as caught:
        await provider.synthesize(_request(cast(SpeechLanguage, "hak-TW")))

    assert caught.value.category == ProviderErrorCategory.UNSUPPORTED_LANGUAGE
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (401, ProviderErrorCategory.MISCONFIGURED),
        (403, ProviderErrorCategory.MISCONFIGURED),
        (400, ProviderErrorCategory.INVALID_RESPONSE),
        (415, ProviderErrorCategory.INVALID_RESPONSE),
        (429, ProviderErrorCategory.UNAVAILABLE),
        (502, ProviderErrorCategory.UNAVAILABLE),
        (503, ProviderErrorCategory.UNAVAILABLE),
    ],
)
async def test_http_failures_are_bounded_without_body_leakage(
    status_code: int,
    category: ProviderErrorCategory,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status_code, text="restricted upstream body key=secret")

    with pytest.raises(SpeechProviderError) as caught:
        await _provider(handler).synthesize(_request())

    assert caught.value.category == category
    assert "restricted upstream body" not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_transport_timeout_has_bounded_category() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("restricted timeout detail", request=request)

    with pytest.raises(SpeechProviderError) as caught:
        await _provider(handler).synthesize(_request())

    assert caught.value.category == ProviderErrorCategory.TIMEOUT
    assert "restricted timeout detail" not in str(caught.value)


@pytest.mark.asyncio
async def test_network_failure_has_bounded_unavailable_category() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("restricted network detail", request=request)

    with pytest.raises(SpeechProviderError) as caught:
        await _provider(handler).synthesize(_request())

    assert caught.value.category == ProviderErrorCategory.UNAVAILABLE
    assert "restricted network detail" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"", headers={"Content-Type": "audio/mpeg"}),
        httpx.Response(200, content=b"not-audio", headers={"Content-Type": "text/plain"}),
    ],
)
async def test_malformed_success_response_is_rejected(response: httpx.Response) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return response

    with pytest.raises(SpeechProviderError) as caught:
        await _provider(handler).synthesize(_request())

    assert caught.value.category == ProviderErrorCategory.INVALID_RESPONSE


def test_runtime_route_cannot_send_hakka_to_azure() -> None:
    settings = Settings(TTS_PROVIDER_HAK_TW="azure-speech-tts")

    with pytest.raises(ProviderConfigurationError, match="does not support hak-TW"):
        _build_provider_router(settings)


@pytest.mark.asyncio
async def test_default_managed_tts_route_is_azure_and_fails_closed_without_key() -> None:
    settings = Settings.model_construct(
        AZURE_SPEECH_KEY="",
        AZURE_SPEECH_REGION="",
    )
    router = _build_provider_router(settings)

    with pytest.raises(SpeechProviderError) as caught:
        await router.synthesize(_request("en-US"))

    assert caught.value.provider_key == "azure-speech-tts"
    assert caught.value.category == ProviderErrorCategory.MISCONFIGURED
