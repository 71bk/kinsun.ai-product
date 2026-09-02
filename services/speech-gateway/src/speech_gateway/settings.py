from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from speech_gateway.models import SpeechLanguage

SERVICE_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    # Consumed only when an AWS adapter is explicitly routed. There is no
    # current AWS deployment; speech provider migration is tracked separately.
    AWS_REGION: str = "us-west-2"

    # Hokkien (nan-TW) and Hakka (hak-TW) ASR run on a self-hosted SageMaker
    # endpoint. When unset, those languages are refused rather than answered by
    # the Mandarin model, which would put words in an elder's mouth.
    SAGEMAKER_ASR_ENDPOINT: str | None = None
    # Optional private endpoint for Hokkien/Hakka synthesis. Requests fail
    # closed when it is unset; they never fall back to a Mandarin voice.
    SAGEMAKER_TTS_ENDPOINT: str | None = None

    # Provider selection is server-owned and deliberately split by language.
    # These keys are validated against the in-process registry before the app
    # starts; provider names never come from a browser request.
    ASR_PROVIDER_ZH_TW: str = "aws-transcribe"
    ASR_PROVIDER_EN_US: str = "aws-transcribe"
    ASR_PROVIDER_NAN_TW: str = "aws-sagemaker"
    ASR_PROVIDER_HAK_TW: str = "aws-sagemaker"
    TTS_PROVIDER_ZH_TW: str = "azure-speech-tts"
    TTS_PROVIDER_EN_US: str = "azure-speech-tts"
    TTS_PROVIDER_NAN_TW: str = "aws-sagemaker"
    TTS_PROVIDER_HAK_TW: str = "aws-sagemaker"
    ASR_PROVIDER_TIMEOUT_SECONDS: float = 30.0
    TTS_PROVIDER_TIMEOUT_SECONDS: float = 30.0

    # Deepgram remains opt-in by route. The key is intentionally allowed to be
    # blank while another ASR provider is selected, then fails closed on first
    # Deepgram use. It must come from the deployment secret mechanism.
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_API_BASE_URL: str = "https://api.deepgram.com"

    # Azure Speech TTS is the managed Mandarin/English synthesis route. The
    # credential and region may remain blank while another provider is routed,
    # but a selected Azure route fails closed on first use without both.
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""
    AZURE_SPEECH_TTS_VOICE_ZH_TW: str = "zh-TW-HsiaoChenNeural"
    AZURE_SPEECH_TTS_VOICE_EN_US: str = "en-US-JennyNeural"

    # Core is the only threshold and formal-state authority. Local/Gate 1 calls
    # use an independent short-lived credential bound to method, path, body and correlation.
    # The legacy bearer setting remains migration-only and must not be logged.
    CORE_API_BASE_URL: str = "http://127.0.0.1:8000"
    CORE_API_SERVICE_TOKEN: str = ""
    CORE_API_SERVICE_IDENTITY_ENABLED: bool = False
    CORE_API_SERVICE_IDENTITY_HMAC_SECRET: str = ""
    CORE_API_SERVICE_IDENTITY_ISSUER: str = "kinsun-local"
    CORE_API_SERVICE_IDENTITY_TTL_SECONDS: int = 30
    CORE_API_TIMEOUT_SECONDS: float = 5.0

    model_config = SettingsConfigDict(
        env_file=(SERVICE_ENV_FILE,),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_core_service_identity(self) -> Settings:
        if self.CORE_API_SERVICE_IDENTITY_ENABLED:
            if len(self.CORE_API_SERVICE_IDENTITY_HMAC_SECRET.encode("utf-8")) < 32:
                raise ValueError(
                    "CORE_API_SERVICE_IDENTITY_HMAC_SECRET must contain at least 32 bytes"
                )
            if not 1 <= self.CORE_API_SERVICE_IDENTITY_TTL_SECONDS <= 60:
                raise ValueError("CORE_API_SERVICE_IDENTITY_TTL_SECONDS must be between 1 and 60")
            if self.CORE_API_SERVICE_TOKEN:
                raise ValueError(
                    "CORE_API_SERVICE_TOKEN and request-bound service identity "
                    "are mutually exclusive"
                )
        return self

    def asr_provider_routes(self) -> dict[SpeechLanguage, str]:
        return {
            "zh-TW": self.ASR_PROVIDER_ZH_TW,
            "en-US": self.ASR_PROVIDER_EN_US,
            "nan-TW": self.ASR_PROVIDER_NAN_TW,
            "hak-TW": self.ASR_PROVIDER_HAK_TW,
        }

    def tts_provider_routes(self) -> dict[SpeechLanguage, str]:
        return {
            "zh-TW": self.TTS_PROVIDER_ZH_TW,
            "en-US": self.TTS_PROVIDER_EN_US,
            "nan-TW": self.TTS_PROVIDER_NAN_TW,
            "hak-TW": self.TTS_PROVIDER_HAK_TW,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
