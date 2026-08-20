"""Azure AI Speech REST adapter for Mandarin and English synthesis."""

from __future__ import annotations

import re
from collections.abc import Mapping
from xml.sax.saxutils import escape

import httpx

from speech_gateway.models import SpeakingSpeed, SpeechLanguage
from speech_gateway.provider_contracts import (
    ProviderErrorCategory,
    ProviderMetadata,
    SpeechProviderError,
    TtsProviderRequest,
    TtsProviderResult,
)

_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
_CONTENT_TYPE = "audio/mpeg"
_MAX_AUDIO_BYTES = 10 * 1024 * 1024
_SAFE_REGION = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$")
_SAFE_VOICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SPEED_RATES: Mapping[SpeakingSpeed, str] = {
    "slow": "-20%",
    "normal": "0%",
    "fast": "+20%",
}


class AzureSpeechTtsProvider:
    """Server-owned Azure Speech adapter with a fixed MP3 output policy."""

    key = "azure-speech-tts"
    supported_languages: frozenset[SpeechLanguage] = frozenset({"zh-TW", "en-US"})

    def __init__(
        self,
        *,
        subscription_key: str,
        region: str,
        voice_zh_tw: str,
        voice_en_us: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._subscription_key = subscription_key.strip()
        self._region = region.strip().lower()
        self._voices: dict[SpeechLanguage, str] = {
            "zh-TW": voice_zh_tw.strip(),
            "en-US": voice_en_us.strip(),
        }
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def synthesize(self, request: TtsProviderRequest) -> TtsProviderResult:
        if request.language not in self.supported_languages:
            raise SpeechProviderError(self.key, ProviderErrorCategory.UNSUPPORTED_LANGUAGE)

        voice = self._voices[request.language]
        if (
            not self._subscription_key
            or not _valid_region(self._region)
            or not _SAFE_VOICE.fullmatch(voice)
        ):
            raise SpeechProviderError(self.key, ProviderErrorCategory.MISCONFIGURED)

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    _regional_endpoint(self._region),
                    headers={
                        "Ocp-Apim-Subscription-Key": self._subscription_key,
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": _OUTPUT_FORMAT,
                        "User-Agent": "kinsun-speech-gateway",
                    },
                    content=_ssml(request, voice).encode("utf-8"),
                )
        except httpx.TimeoutException as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.TIMEOUT) from exc
        except httpx.RequestError as exc:
            raise SpeechProviderError(self.key, ProviderErrorCategory.UNAVAILABLE) from exc

        if response.status_code in {401, 403}:
            raise SpeechProviderError(self.key, ProviderErrorCategory.MISCONFIGURED)
        if response.status_code == 429 or response.status_code >= 500:
            raise SpeechProviderError(self.key, ProviderErrorCategory.UNAVAILABLE)
        if not 200 <= response.status_code < 300:
            raise SpeechProviderError(self.key, ProviderErrorCategory.INVALID_RESPONSE)

        media_type = response.headers.get("content-type", "").partition(";")[0].strip().lower()
        if (
            media_type != _CONTENT_TYPE
            or not response.content
            or len(response.content) > _MAX_AUDIO_BYTES
        ):
            raise SpeechProviderError(self.key, ProviderErrorCategory.INVALID_RESPONSE)

        return TtsProviderResult(
            audio=response.content,
            content_type=_CONTENT_TYPE,
            voice_id=voice,
            metadata=ProviderMetadata(
                provider_key=self.key,
                model_version=f"azure-speech:{voice}",
            ),
        )


def _valid_region(region: str) -> bool:
    return len(region) >= 2 and _SAFE_REGION.fullmatch(region) is not None


def _regional_endpoint(region: str) -> str:
    return f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"


def _ssml(request: TtsProviderRequest, voice: str) -> str:
    text = escape(request.text)
    rate = _SPEED_RATES[request.speaking_speed]
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{request.language}">'
        f'<voice name="{voice}"><prosody rate="{rate}">{text}</prosody></voice>'
        "</speak>"
    )
