"""Deepgram Nova-3 adapter for pre-recorded mono linear16 PCM audio."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from speech_gateway.models import SpeechLanguage, TranscriptSegment
from speech_gateway.provider_contracts import (
    AsrProviderRequest,
    AsrProviderResult,
    ProviderErrorCategory,
    ProviderMetadata,
    SpeechProviderError,
)

_MODEL = "nova-3"
_SAFE_MODEL_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class DeepgramNova3AsrProvider:
    """Server-owned Deepgram adapter; callers cannot override its policy."""

    key = "deepgram-nova-3"
    supported_languages: frozenset[SpeechLanguage] = frozenset({"zh-TW", "en-US"})

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._listen_url = _listen_url(base_url)
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def transcribe(self, request: AsrProviderRequest) -> AsrProviderResult:
        if request.language not in self.supported_languages:
            raise SpeechProviderError(self.key, ProviderErrorCategory.UNSUPPORTED_LANGUAGE)
        if not self._api_key:
            raise SpeechProviderError(self.key, ProviderErrorCategory.MISCONFIGURED)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._listen_url,
                    params={
                        "model": _MODEL,
                        "language": request.language,
                        "encoding": "linear16",
                        "sample_rate": str(request.sample_rate),
                        "channels": "1",
                        "smart_format": "true",
                        "mip_opt_out": "true",
                    },
                    headers={
                        "Authorization": f"Token {self._api_key}",
                        "Content-Type": "application/octet-stream",
                    },
                    content=request.audio,
                )
        except httpx.TimeoutException as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.UNAVAILABLE) from exc

        if response.status_code in {401, 403}:
            raise SpeechProviderError(self.key, ProviderErrorCategory.AUTHENTICATION)
        if response.status_code == 429 or response.status_code >= 500:
            raise SpeechProviderError(self.key, ProviderErrorCategory.UNAVAILABLE)
        if not 200 <= response.status_code < 300:
            raise SpeechProviderError(self.key, ProviderErrorCategory.INVALID_RESPONSE)

        try:
            payload = response.json()
            return _parse_response(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.INVALID_RESPONSE) from exc


def _listen_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Deepgram API base URL is invalid")
    return f"{normalized}/v1/listen"


def _parse_response(payload: Any) -> AsrProviderResult:
    if not isinstance(payload, Mapping):
        raise TypeError("response must be an object")
    results = _mapping(payload["results"])
    channels = _non_empty_list(results["channels"])
    channel = _mapping(channels[0])
    alternatives = _non_empty_list(channel["alternatives"])
    alternative = _mapping(alternatives[0])

    text = alternative["transcript"]
    if not isinstance(text, str):
        raise TypeError("transcript must be a string")

    raw_words = alternative.get("words", [])
    if not isinstance(raw_words, list):
        raise TypeError("words must be a list")
    segments = tuple(_segment(word) for word in raw_words)
    if segments:
        confidence = min(segment.confidence for segment in segments)
    else:
        confidence = _probability(alternative["confidence"])

    return AsrProviderResult(
        text=text,
        confidence=confidence,
        segments=segments,
        metadata=ProviderMetadata(
            provider_key=DeepgramNova3AsrProvider.key,
            model_version=_model_version(payload.get("metadata")),
        ),
    )


def _segment(raw_word: Any) -> TranscriptSegment:
    word = _mapping(raw_word)
    plain_text = word["word"]
    punctuated_text = word.get("punctuated_word")
    if not isinstance(plain_text, str) or not plain_text:
        raise TypeError("word must be a non-empty string")
    if punctuated_text is not None and not isinstance(punctuated_text, str):
        raise TypeError("punctuated_word must be a string")

    start_time = _finite_number(word["start"])
    end_time = _finite_number(word["end"])
    if start_time < 0 or end_time < start_time:
        raise ValueError("word timings are invalid")

    return TranscriptSegment(
        text=punctuated_text or plain_text,
        start_time=start_time,
        end_time=end_time,
        confidence=_probability(word["confidence"]),
    )


def _model_version(metadata: Any) -> str:
    if not isinstance(metadata, Mapping):
        return _MODEL
    models = metadata.get("models")
    model_info = metadata.get("model_info")
    if not isinstance(models, list) or not models or not isinstance(model_info, Mapping):
        return _MODEL
    model_id = models[0]
    if not isinstance(model_id, str):
        return _MODEL
    info = model_info.get(model_id)
    if not isinstance(info, Mapping):
        return _MODEL

    architecture = info.get("arch")
    version = info.get("version")
    if not isinstance(architecture, str) or not _SAFE_MODEL_PART.fullmatch(architecture):
        architecture = _MODEL
    if not isinstance(version, str) or not _SAFE_MODEL_PART.fullmatch(version):
        return architecture
    return f"{architecture}:{version}"


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("value must be an object")
    return value


def _non_empty_list(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise TypeError("value must be a non-empty list")
    return value


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("value must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("value must be finite")
    return result


def _probability(value: Any) -> float:
    result = _finite_number(value)
    if not 0 <= result <= 1:
        raise ValueError("confidence must be between zero and one")
    return result
