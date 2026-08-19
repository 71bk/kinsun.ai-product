from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from speech_gateway.models import SpeechLanguage

SERVICE_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
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
    TTS_PROVIDER_ZH_TW: str = "aws-polly"
    TTS_PROVIDER_EN_US: str = "aws-polly"
    TTS_PROVIDER_NAN_TW: str = "aws-sagemaker"
    TTS_PROVIDER_HAK_TW: str = "aws-sagemaker"
    ASR_PROVIDER_TIMEOUT_SECONDS: float = 30.0
    TTS_PROVIDER_TIMEOUT_SECONDS: float = 30.0

    # Core is the only threshold and formal-state authority. This bearer value
    # is a Core-issued service credential, not
    # a browser token, and must never be returned or logged.
    CORE_API_BASE_URL: str = "http://127.0.0.1:8000"
    CORE_API_SERVICE_TOKEN: str = ""
    CORE_API_TIMEOUT_SECONDS: float = 5.0

    model_config = SettingsConfigDict(
        env_file=(SERVICE_ENV_FILE,),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

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
