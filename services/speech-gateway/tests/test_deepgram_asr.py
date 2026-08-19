"""Deepgram adapter tests use synthetic PCM and an in-memory HTTP transport."""

from __future__ import annotations

from typing import cast

import httpx
import pytest

from speech_gateway.app import _build_provider_router
from speech_gateway.deepgram_asr import DeepgramNova3AsrProvider
from speech_gateway.models import SpeechLanguage
from speech_gateway.provider_contracts import (
    AsrProviderRequest,
    ProviderErrorCategory,
    SpeechProviderError,
)
from speech_gateway.provider_router import ProviderConfigurationError
from speech_gateway.settings import Settings

SYNTHETIC_PCM = b"\x01\x00\x02\x00"


def _request(language: SpeechLanguage = "zh-TW") -> AsrProviderRequest:
    return AsrProviderRequest(audio=SYNTHETIC_PCM, language=language, sample_rate=16000)


def _success_payload() -> dict[str, object]:
    model_id = "synthetic-model-id"
    return {
        "metadata": {
            "models": [model_id],
            "model_info": {
                model_id: {
                    "name": "general",
                    "version": "2025-07-31.0",
                    "arch": "nova-3",
                }
            },
        },
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "合成 測試。",
                            "confidence": 0.99,
                            "words": [
                                {
                                    "word": "合成",
                                    "punctuated_word": "合成",
                                    "start": 0.0,
                                    "end": 0.25,
                                    "confidence": 0.94,
                                },
                                {
                                    "word": "測試",
                                    "punctuated_word": "測試。",
                                    "start": 0.25,
                                    "end": 0.6,
                                    "confidence": 0.81,
                                },
                            ],
                        }
                    ]
                }
            ]
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["zh-TW", "en-US"])
async def test_request_policy_is_server_owned_and_response_is_normalized(
    language: SpeechLanguage,
) -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=_success_payload())

    provider = DeepgramNova3AsrProvider(
        api_key="synthetic-api-key",
        base_url="https://deepgram.test/private-prefix",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    result = await provider.transcribe(_request(language))

    assert len(captured) == 1
    upstream = captured[0]
    assert upstream.method == "POST"
    assert upstream.url.path == "/private-prefix/v1/listen"
    assert upstream.headers["authorization"] == "Token synthetic-api-key"
    assert upstream.headers["content-type"] == "application/octet-stream"
    assert upstream.content == SYNTHETIC_PCM
    assert dict(upstream.url.params) == {
        "model": "nova-3",
        "language": language,
        "encoding": "linear16",
        "sample_rate": "16000",
        "channels": "1",
        "smart_format": "true",
        "mip_opt_out": "true",
    }
    assert result.text == "合成 測試。"
    assert result.confidence == 0.81
    assert [segment.text for segment in result.segments] == ["合成", "測試。"]
    assert result.metadata.provider_key == "deepgram-nova-3"
    assert result.metadata.model_version == "nova-3:2025-07-31.0"


@pytest.mark.asyncio
async def test_missing_api_key_fails_closed_before_an_http_request() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_success_payload())

    provider = DeepgramNova3AsrProvider(
        api_key="",
        base_url="https://deepgram.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SpeechProviderError) as caught:
        await provider.transcribe(_request())

    assert caught.value.category == ProviderErrorCategory.MISCONFIGURED
    assert calls == 0


@pytest.mark.asyncio
async def test_low_resource_language_is_refused_before_an_http_request() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_success_payload())

    provider = DeepgramNova3AsrProvider(
        api_key="synthetic-api-key",
        base_url="https://deepgram.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SpeechProviderError) as caught:
        await provider.transcribe(_request(cast(SpeechLanguage, "nan-TW")))

    assert caught.value.category == ProviderErrorCategory.UNSUPPORTED_LANGUAGE
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (401, ProviderErrorCategory.MISCONFIGURED),
        (403, ProviderErrorCategory.MISCONFIGURED),
        (400, ProviderErrorCategory.INVALID_RESPONSE),
        (429, ProviderErrorCategory.UNAVAILABLE),
        (503, ProviderErrorCategory.UNAVAILABLE),
    ],
)
async def test_http_failures_are_bounded_without_upstream_body_leakage(
    status_code: int,
    category: ProviderErrorCategory,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status_code, text="restricted-upstream-body token=secret")

    provider = DeepgramNova3AsrProvider(
        api_key="synthetic-api-key",
        base_url="https://deepgram.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SpeechProviderError) as caught:
        await provider.transcribe(_request())

    assert caught.value.category == category
    assert "restricted-upstream-body" not in str(caught.value)
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
async def test_transport_timeout_has_a_bounded_timeout_category() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("restricted timeout detail", request=request)

    provider = DeepgramNova3AsrProvider(
        api_key="synthetic-api-key",
        base_url="https://deepgram.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SpeechProviderError) as caught:
        await provider.transcribe(_request())

    assert caught.value.category == ProviderErrorCategory.TIMEOUT
    assert "restricted timeout detail" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"results": {"channels": []}}),
        httpx.Response(
            200,
            json={"results": {"channels": [{"alternatives": [{"transcript": "synthetic"}]}]}},
        ),
    ],
)
async def test_malformed_success_response_is_rejected(response: httpx.Response) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return response

    provider = DeepgramNova3AsrProvider(
        api_key="synthetic-api-key",
        base_url="https://deepgram.test",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SpeechProviderError) as caught:
        await provider.transcribe(_request())

    assert caught.value.category == ProviderErrorCategory.INVALID_RESPONSE


def test_invalid_base_url_is_rejected_during_construction() -> None:
    with pytest.raises(ValueError, match="base URL is invalid"):
        DeepgramNova3AsrProvider(
            api_key="synthetic-api-key",
            base_url="https://user:password@deepgram.test?secret=value",
            timeout_seconds=1,
        )


def test_runtime_route_cannot_send_hokkien_to_deepgram() -> None:
    settings = Settings(
        ASR_PROVIDER_NAN_TW="deepgram-nova-3",
        DEEPGRAM_API_BASE_URL="https://deepgram.test",
    )

    with pytest.raises(ProviderConfigurationError, match="does not support nan-TW"):
        _build_provider_router(settings)
