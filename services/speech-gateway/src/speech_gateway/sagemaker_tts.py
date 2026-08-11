"""SageMaker TTS adapter for Hokkien (nan-TW) and Hakka (hak-TW)."""

from __future__ import annotations

import asyncio
import json

from speech_gateway.models import SageMakerLanguage, SpeakingSpeed

MODEL_VERSION_UNKNOWN = "sagemaker-unknown"


class SageMakerTtsNotConfiguredError(RuntimeError):
    """Raised when no low-resource TTS endpoint is configured."""


async def synthesize_via_sagemaker(
    text: str,
    language: SageMakerLanguage,
    speaking_speed: SpeakingSpeed,
    region: str,
    endpoint_name: str | None,
) -> tuple[bytes, str, str]:
    """Invoke the private endpoint and return audio, content type and model id."""
    if not endpoint_name:
        raise SageMakerTtsNotConfiguredError(
            "no SageMaker TTS endpoint is configured for this language"
        )

    import boto3

    client = boto3.client("sagemaker-runtime", region_name=region)

    def call() -> dict:
        return client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=json.dumps(
                {
                    "text": text,
                    "language": language,
                    "speakingSpeed": speaking_speed,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )

    response = await asyncio.to_thread(call)
    body = response.get("Body")
    if body is None:
        raise RuntimeError("SageMaker TTS returned no audio stream")

    audio = body.read()
    if not audio:
        raise RuntimeError("SageMaker TTS returned empty audio")

    content_type = response.get("ContentType") or "audio/wav"
    if not content_type.startswith("audio/"):
        raise RuntimeError("SageMaker TTS returned an invalid content type")
    if content_type in {"audio/wav", "audio/x-wav"} and not audio.startswith(b"RIFF"):
        raise RuntimeError("SageMaker TTS returned an invalid WAV payload")

    model_version = response.get("CustomAttributes") or MODEL_VERSION_UNKNOWN
    return audio, content_type, model_version
