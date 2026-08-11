from __future__ import annotations

import json
from io import BytesIO

import boto3
import pytest

from speech_gateway.sagemaker_tts import (
    SageMakerTtsNotConfiguredError,
    synthesize_via_sagemaker,
)


@pytest.mark.asyncio
async def test_sagemaker_tts_fails_closed_without_endpoint() -> None:
    with pytest.raises(SageMakerTtsNotConfiguredError):
        await synthesize_via_sagemaker(
            "synthetic text",
            "nan-TW",
            "normal",
            "us-west-2",
            None,
        )


@pytest.mark.asyncio
async def test_sagemaker_tts_uses_minimized_private_endpoint_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def invoke_endpoint(self, **kwargs):  # noqa: ANN003, ANN201
            captured.update(kwargs)
            return {
                "Body": BytesIO(b"RIFFsynthetic-wav"),
                "ContentType": "audio/wav",
                "CustomAttributes": "synthetic-tts-v1",
            }

    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: FakeClient())

    audio, content_type, model_version = await synthesize_via_sagemaker(
        "逐家好",
        "nan-TW",
        "slow",
        "us-west-2",
        "kinsun-speech-tts-v1",
    )

    assert audio == b"RIFFsynthetic-wav"
    assert content_type == "audio/wav"
    assert model_version == "synthetic-tts-v1"
    assert captured["EndpointName"] == "kinsun-speech-tts-v1"
    assert captured["ContentType"] == "application/json"
    assert json.loads(captured["Body"]) == {
        "text": "逐家好",
        "language": "nan-TW",
        "speakingSpeed": "slow",
    }
