from __future__ import annotations

import pytest
from pydantic import ValidationError

from speech_gateway.settings import Settings


def test_production_requires_request_bound_core_identity_and_ip_hash_secret() -> None:
    with pytest.raises(ValidationError, match="CORE_API_SERVICE_IDENTITY_ENABLED"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            TTS_CLIENT_IP_HASH_SECRET="independent-client-ip-secret-material-at-least-32-bytes",
        )
    with pytest.raises(ValidationError, match="TTS_CLIENT_IP_HASH_SECRET"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            CORE_API_SERVICE_IDENTITY_ENABLED=True,
            CORE_API_SERVICE_IDENTITY_HMAC_SECRET=(
                "speech-service-identity-secret-material-at-least-32-bytes"
            ),
        )


def test_production_accepts_independent_tts_security_secrets() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        CORE_API_SERVICE_IDENTITY_ENABLED=True,
        CORE_API_SERVICE_IDENTITY_HMAC_SECRET=(
            "speech-service-identity-secret-material-at-least-32-bytes"
        ),
        TTS_CLIENT_IP_HASH_SECRET="independent-client-ip-secret-material-at-least-32-bytes",
    )

    assert settings.TTS_MAX_CONCURRENCY == 4


def test_ip_hash_secret_must_not_reuse_service_identity_secret() -> None:
    shared = "shared-speech-security-secret-material-at-least-32-bytes"
    with pytest.raises(ValidationError, match="must be independent"):
        Settings(
            _env_file=None,
            CORE_API_SERVICE_IDENTITY_ENABLED=True,
            CORE_API_SERVICE_IDENTITY_HMAC_SECRET=shared,
            TTS_CLIENT_IP_HASH_SECRET=shared,
        )
