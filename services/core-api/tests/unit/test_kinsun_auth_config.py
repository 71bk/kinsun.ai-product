from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_BASE = {
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/testdb",
    "APP_SESSION_AUTH_ENABLED": "true",
    "KINSUN_NATIVE_AUTH_ENABLED": "true",
    "KINSUN_IDENTITY_HMAC_SECRET": "kinsun-identity-config-secret-material-32-bytes",
    "KINSUN_EMAIL_CHALLENGE_HMAC_SECRET": "kinsun-challenge-config-secret-material-32-bytes",
    "KINSUN_AUTH_HANDOFF_SECRET": "kinsun-handoff-config-secret-material-32-bytes",
    "FAMILY_INVITATION_HMAC_SECRET": "kinsun-family-config-secret-material-32-bytes",
    "KINSUN_EMAIL_DELIVERY_MODE": "synthetic",
    "KINSUN_SYNTHETIC_EMAIL_CODE_SECRET": "246810",
}


def _settings(**overrides: str) -> Settings:
    values = {**_BASE, **overrides}
    with patch.dict(os.environ, values, clear=True):
        return Settings(_env_file=None)


def test_development_synthetic_native_auth_is_valid() -> None:
    settings = _settings(APP_ENV="development")

    assert settings.kinsun_native_auth_enabled is True
    assert settings.kinsun_email_delivery_mode == "synthetic"


def test_production_rejects_synthetic_delivery() -> None:
    with pytest.raises(ValidationError, match="forbidden in production"):
        _settings(APP_ENV="production")


def test_native_auth_requires_app_session_gate() -> None:
    with pytest.raises(ValidationError, match="APP_SESSION_AUTH_ENABLED"):
        _settings(APP_ENV="development", APP_SESSION_AUTH_ENABLED="false")


def test_native_auth_requires_independent_secrets() -> None:
    with pytest.raises(ValidationError, match="independent"):
        _settings(
            APP_ENV="development",
            KINSUN_EMAIL_CHALLENGE_HMAC_SECRET=_BASE["KINSUN_IDENTITY_HMAC_SECRET"],
        )
