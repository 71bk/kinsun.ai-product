"""Unit tests for app.core.config — Settings Manager."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import AppEnv, DatabasePoolMode, Settings, get_settings

# ─── Helpers ─────────────────────────────────────────────────────────────────

_VALID_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/testdb"


def _make_settings(**overrides: str) -> Settings:
    """Create Settings with environment variable overrides (no .env file)."""
    env = {
        "APP_ENV": "development",
        "DATABASE_URL": _VALID_DB_URL,
    }
    env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        return Settings(_env_file=None)


# ─── Basic construction ──────────────────────────────────────────────────────


class TestSettingsConstruction:
    def test_valid_settings(self) -> None:
        s = _make_settings()
        assert s.app_env == AppEnv.DEVELOPMENT
        assert s.database_url == _VALID_DB_URL
        assert s.app_title == "kinsun.ai Core API"
        assert s.app_version == "0.1.0"
        assert s.port == 8000
        assert s.db_pool_mode == DatabasePoolMode.QUEUE
        assert s.db_pool_size == 5
        assert s.db_max_overflow == 10
        assert s.db_connect_timeout_seconds == 5.0
        assert s.db_recovery_timeout_seconds == 10.0

    def test_production_env(self) -> None:
        s = _make_settings(APP_ENV="production")
        assert s.app_env == AppEnv.PRODUCTION

    def test_google_client_secret_is_not_a_core_setting(self) -> None:
        s = _make_settings(GOOGLE_OIDC_CLIENT_SECRET="bff-only-secret")

        assert not hasattr(s, "google_oidc_client_secret")

    def test_all_fields_settable(self) -> None:
        s = _make_settings(
            APP_TITLE="Custom Title",
            APP_VERSION="2.0.0",
            DOCS_URL="/api-docs",
            HOST="127.0.0.1",
            PORT="9000",
            DB_POOL_MODE="null",
            DB_POOL_SIZE="10",
            DB_MAX_OVERFLOW="20",
            DB_CONNECT_TIMEOUT_SECONDS="4",
            DB_RECOVERY_TIMEOUT_SECONDS="9",
            TEST_DATABASE_URL="postgresql+asyncpg://x:y@host/test",
            DATABASE_PASSWORD="supersecret",
            FAKE_AUTH_ENABLED="true",
            FAKE_AUTH_ACTOR_ID="20000000-0000-4000-8000-000000000001",
            FAKE_AUTH_TENANT_ID="10000000-0000-4000-8000-000000000001",
            FAKE_AUTH_ACTOR_ROLE="ELDER",
            FAMILY_INVITATION_HMAC_SECRET="test-family-invitation-secret-32-bytes",
            GOOGLE_OIDC_CLIENT_ID="google-web-client.apps.googleusercontent.com",
            GOOGLE_OIDC_JWKS_CACHE_SECONDS="180",
            GOOGLE_OIDC_HTTP_TIMEOUT_SECONDS="4",
            GOOGLE_IDENTITY_HMAC_SECRET="google-identity-secret-material-at-least-32-bytes",
            GOOGLE_IDENTITY_HMAC_KEY_VERSION="1",
            GOOGLE_OIDC_HANDOFF_SECRET="google-handoff-secret-material-at-least-32-bytes",
            GOOGLE_PENDING_IDENTITY_TTL_SECONDS="300",
            APP_SESSION_ELDER_FAMILY_IDLE_TTL_SECONDS="1200",
            APP_SESSION_ELDER_FAMILY_ABSOLUTE_TTL_SECONDS="2400",
            APP_SESSION_WORKFORCE_IDLE_TTL_SECONDS="600",
            APP_SESSION_WORKFORCE_ABSOLUTE_TTL_SECONDS="1800",
            APP_SESSION_TOUCH_INTERVAL_SECONDS="60",
            APP_SESSION_RECENT_AUTH_WINDOW_SECONDS="120",
            APP_SESSION_MAX_ACTIVE_PER_ACTOR="3",
            VOICE_TICKET_ENABLED="true",
            VOICE_TICKET_HMAC_SECRET="test-voice-ticket-secret-material-32-bytes",
            VOICE_TICKET_TTL_SECONDS="75",
            ASR_GATE_ENABLED="true",
            ASR_GATE_HMAC_SECRET="test-independent-asr-gate-secret-material-32-bytes",
            ASR_GATE_CONFIDENCE_THRESHOLD="0.8",
            ASR_GATE_EVIDENCE_TTL_SECONDS="600",
            AGENT_RUNTIME_URL="http://127.0.0.1:8001",
            AGENT_RUNTIME_TIMEOUT_SECONDS="8",
            AGENT_RUNTIME_MODEL_ID="mock-v1",
            SPEECH_SERVICE_IDENTITY_ENABLED="true",
            SPEECH_SERVICE_IDENTITY_HMAC_SECRET=(
                "speech-core-service-identity-secret-material-32-bytes"
            ),
            SPEECH_SERVICE_IDENTITY_ISSUER="kinsun-speech-test",
            SPEECH_SERVICE_IDENTITY_TTL_SECONDS="20",
            EVIDENCE_AWARE_MEMORY="true",
            AUTO_LOW_RISK_MEMORY="true",
        )
        assert s.app_title == "Custom Title"
        assert s.app_version == "2.0.0"
        assert s.docs_url == "/api-docs"
        assert s.host == "127.0.0.1"
        assert s.port == 9000
        assert s.db_pool_mode == DatabasePoolMode.NULL
        assert s.db_pool_size == 10
        assert s.db_max_overflow == 20
        assert s.db_connect_timeout_seconds == 4
        assert s.db_recovery_timeout_seconds == 9
        assert s.test_database_url == "postgresql+asyncpg://x:y@host/test"
        assert s.database_password == "supersecret"
        assert s.fake_auth_enabled is True
        assert str(s.fake_auth_actor_id) == "20000000-0000-4000-8000-000000000001"
        assert str(s.fake_auth_tenant_id) == "10000000-0000-4000-8000-000000000001"
        assert s.fake_auth_actor_role == "ELDER"
        assert s.family_invitation_hmac_secret == "test-family-invitation-secret-32-bytes"
        assert s.google_oidc_client_id == "google-web-client.apps.googleusercontent.com"
        assert s.google_oidc_jwks_cache_seconds == 180
        assert s.google_oidc_http_timeout_seconds == 4
        assert s.google_identity_hmac_secret == (
            "google-identity-secret-material-at-least-32-bytes"
        )
        assert s.google_identity_hmac_key_version == 1
        assert s.google_oidc_handoff_secret == "google-handoff-secret-material-at-least-32-bytes"
        assert s.google_pending_identity_ttl_seconds == 300
        assert s.app_session_elder_family_idle_ttl_seconds == 1200
        assert s.app_session_elder_family_absolute_ttl_seconds == 2400
        assert s.app_session_workforce_idle_ttl_seconds == 600
        assert s.app_session_workforce_absolute_ttl_seconds == 1800
        assert s.app_session_touch_interval_seconds == 60
        assert s.app_session_recent_auth_window_seconds == 120
        assert s.app_session_max_active_per_actor == 3
        assert s.voice_ticket_enabled is True
        assert s.voice_ticket_hmac_secret == "test-voice-ticket-secret-material-32-bytes"
        assert s.voice_ticket_ttl_seconds == 75
        assert s.asr_gate_enabled is True
        assert s.asr_gate_confidence_threshold == 0.8
        assert s.asr_gate_evidence_ttl_seconds == 600
        assert s.agent_runtime_url == "http://127.0.0.1:8001"
        assert s.agent_runtime_timeout_seconds == 8
        assert s.agent_runtime_model_id == "mock-v1"
        assert s.speech_service_identity_enabled is True
        assert s.speech_service_identity_issuer == "kinsun-speech-test"
        assert s.speech_service_identity_ttl_seconds == 20
        assert s.evidence_aware_memory is True
        assert s.auto_low_risk_memory is True

    def test_memory_rollout_flags_default_off(self) -> None:
        s = _make_settings(
            EVIDENCE_AWARE_MEMORY="false",
            AUTO_LOW_RISK_MEMORY="false",
        )

        assert s.evidence_aware_memory is False
        assert s.auto_low_risk_memory is False

    def test_assisted_elder_session_rollout_defaults_off(self) -> None:
        settings = _make_settings()

        assert settings.assisted_elder_sessions_enabled is False
        assert settings.care_profile_ai_context_enabled is False
        assert settings.assisted_elder_pairing_ttl_seconds == 600
        assert settings.assisted_elder_idle_ttl_seconds == 1800
        assert settings.assisted_elder_absolute_ttl_seconds == 28800
        assert settings.assisted_elder_acknowledgement_policy_version == "demo-consent-v1"

    def test_assisted_elder_session_rollout_is_non_production_only(self) -> None:
        with pytest.raises(ValidationError, match="non-production"):
            _make_settings(
                APP_ENV="production",
                ASSISTED_ELDER_SESSIONS_ENABLED="true",
            )

        with pytest.raises(ValidationError, match="non-production"):
            _make_settings(
                APP_ENV="production",
                CARE_PROFILE_AI_CONTEXT_ENABLED="true",
            )

    def test_assisted_elder_idle_ttl_must_not_exceed_absolute_ttl(self) -> None:
        with pytest.raises(ValidationError, match="Assisted Elder Session idle TTL"):
            _make_settings(
                ASSISTED_ELDER_IDLE_TTL_SECONDS="3600",
                ASSISTED_ELDER_ABSOLUTE_TTL_SECONDS="1800",
            )

    def test_auto_low_memory_requires_parent_rollout_gate(self) -> None:
        with pytest.raises(ValidationError, match="EVIDENCE_AWARE_MEMORY"):
            _make_settings(
                EVIDENCE_AWARE_MEMORY="false",
                AUTO_LOW_RISK_MEMORY="true",
            )


# ─── Validation errors ───────────────────────────────────────────────────────


class TestValidation:
    def test_missing_database_url_raises(self) -> None:
        """Required field missing raises validation error identifying the variable."""
        env = {"APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)
            errors = exc_info.value.errors()
            field_names = [e["loc"][-1] for e in errors]
            assert "database_url" in field_names

    def test_invalid_database_url_scheme(self) -> None:
        """DATABASE_URL without postgresql+asyncpg:// is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            _make_settings(DATABASE_URL="mysql://user:pass@localhost/db")
        errors = exc_info.value.errors()
        assert any("postgresql+asyncpg://" in str(e) for e in errors)

    def test_port_too_low(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(PORT="0")

    def test_port_too_high(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(PORT="65536")

    def test_port_boundaries_valid(self) -> None:
        s = _make_settings(PORT="1")
        assert s.port == 1
        s = _make_settings(PORT="65535")
        assert s.port == 65535

    def test_invalid_app_env_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(APP_ENV="staging")

    def test_db_pool_size_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DB_POOL_SIZE="0")

    def test_db_max_overflow_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DB_MAX_OVERFLOW="-1")

    def test_invalid_db_pool_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_settings(DB_POOL_MODE="unsupported")

    @pytest.mark.parametrize(
        "field",
        ["DB_CONNECT_TIMEOUT_SECONDS", "DB_RECOVERY_TIMEOUT_SECONDS"],
    )
    def test_database_timeouts_must_be_positive(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _make_settings(**{field: "0"})

    @pytest.mark.parametrize(
        ("idle_field", "absolute_field"),
        [
            (
                "APP_SESSION_ELDER_FAMILY_IDLE_TTL_SECONDS",
                "APP_SESSION_ELDER_FAMILY_ABSOLUTE_TTL_SECONDS",
            ),
            (
                "APP_SESSION_WORKFORCE_IDLE_TTL_SECONDS",
                "APP_SESSION_WORKFORCE_ABSOLUTE_TTL_SECONDS",
            ),
        ],
    )
    def test_app_session_idle_ttl_cannot_exceed_absolute_ttl(
        self,
        idle_field: str,
        absolute_field: str,
    ) -> None:
        with pytest.raises(ValidationError, match="idle TTL"):
            _make_settings(**{idle_field: "601", absolute_field: "600"})

    def test_app_session_touch_interval_must_be_shorter_than_idle_ttls(self) -> None:
        with pytest.raises(ValidationError, match="TOUCH_INTERVAL"):
            _make_settings(
                APP_SESSION_TOUCH_INTERVAL_SECONDS="300",
                APP_SESSION_WORKFORCE_IDLE_TTL_SECONDS="300",
            )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("GOOGLE_OIDC_JWKS_CACHE_SECONDS", "29"),
            ("GOOGLE_OIDC_JWKS_CACHE_SECONDS", "3601"),
            ("GOOGLE_OIDC_HTTP_TIMEOUT_SECONDS", "0"),
            ("GOOGLE_OIDC_HTTP_TIMEOUT_SECONDS", "16"),
        ],
    )
    def test_google_oidc_network_settings_are_bounded(self, field: str, value: str) -> None:
        with pytest.raises(ValidationError):
            _make_settings(**{field: value})

    @pytest.mark.parametrize("ttl", ["59", "901"])
    def test_google_pending_identity_ttl_is_bounded(self, ttl: str) -> None:
        with pytest.raises(ValidationError):
            _make_settings(GOOGLE_PENDING_IDENTITY_TTL_SECONDS=ttl)

    def test_google_identity_key_version_requires_explicit_migration(self) -> None:
        with pytest.raises(ValidationError, match="rekey migration"):
            _make_settings(GOOGLE_IDENTITY_HMAC_KEY_VERSION="2")

    def test_google_identity_and_handoff_secrets_must_be_independent(self) -> None:
        shared = "shared-google-secret-material-at-least-32-bytes"
        with pytest.raises(ValidationError, match="must be independent"):
            _make_settings(
                GOOGLE_IDENTITY_HMAC_SECRET=shared,
                GOOGLE_OIDC_HANDOFF_SECRET=shared,
            )

    def test_google_handoff_requires_app_session_auth_gate(self) -> None:
        with pytest.raises(ValidationError, match="APP_SESSION_AUTH_ENABLED"):
            _make_settings(
                GOOGLE_OIDC_HANDOFF_ENABLED="true",
                GOOGLE_OIDC_CLIENT_ID="google-web-client.apps.googleusercontent.com",
                GOOGLE_IDENTITY_HMAC_SECRET=("google-identity-secret-material-at-least-32-bytes"),
                GOOGLE_OIDC_HANDOFF_SECRET=("google-handoff-secret-material-at-least-32-bytes"),
                FAMILY_INVITATION_HMAC_SECRET=(
                    "test-family-invitation-secret-material-at-least-32-bytes"
                ),
            )

    def test_enabled_google_handoff_requires_independent_purpose_secrets(self) -> None:
        shared = "shared-google-and-family-secret-material-at-least-32-bytes"
        with pytest.raises(ValidationError, match="must be independent"):
            _make_settings(
                APP_SESSION_AUTH_ENABLED="true",
                GOOGLE_OIDC_HANDOFF_ENABLED="true",
                GOOGLE_OIDC_CLIENT_ID="google-web-client.apps.googleusercontent.com",
                GOOGLE_IDENTITY_HMAC_SECRET=shared,
                GOOGLE_OIDC_HANDOFF_SECRET=("google-handoff-secret-material-at-least-32-bytes"),
                FAMILY_INVITATION_HMAC_SECRET=shared,
            )

    def test_enabled_google_handoff_accepts_complete_independent_configuration(self) -> None:
        settings = _make_settings(
            APP_SESSION_AUTH_ENABLED="true",
            GOOGLE_OIDC_HANDOFF_ENABLED="true",
            GOOGLE_OIDC_CLIENT_ID="google-web-client.apps.googleusercontent.com",
            GOOGLE_IDENTITY_HMAC_SECRET=("google-identity-secret-material-at-least-32-bytes"),
            GOOGLE_OIDC_HANDOFF_SECRET=("google-handoff-secret-material-at-least-32-bytes"),
            FAMILY_INVITATION_HMAC_SECRET=(
                "test-family-invitation-secret-material-at-least-32-bytes"
            ),
        )

        assert settings.app_session_auth_enabled is True
        assert settings.google_oidc_handoff_enabled is True

    def test_enabled_line_handoff_requires_app_session_auth(self) -> None:
        with pytest.raises(ValidationError, match="APP_SESSION_AUTH_ENABLED"):
            _make_settings(
                LINE_OIDC_HANDOFF_ENABLED="true",
                LINE_LOGIN_CHANNEL_ID="1234567890",
                LINE_IDENTITY_HMAC_SECRET=("line-identity-secret-material-at-least-32-bytes"),
                LINE_OIDC_HANDOFF_SECRET=("line-handoff-secret-material-at-least-32-bytes"),
                FAMILY_INVITATION_HMAC_SECRET=("line-family-secret-material-at-least-32-bytes"),
            )

    def test_enabled_line_handoff_accepts_complete_independent_configuration(self) -> None:
        settings = _make_settings(
            APP_SESSION_AUTH_ENABLED="true",
            LINE_OIDC_HANDOFF_ENABLED="true",
            LINE_LOGIN_CHANNEL_ID="1234567890",
            LINE_IDENTITY_HMAC_SECRET=("line-identity-secret-material-at-least-32-bytes"),
            LINE_OIDC_HANDOFF_SECRET=("line-handoff-secret-material-at-least-32-bytes"),
            FAMILY_INVITATION_HMAC_SECRET=("line-family-secret-material-at-least-32-bytes"),
        )

        assert settings.line_oidc_handoff_enabled is True
        assert settings.line_login_channel_id == "1234567890"

    def test_enabled_voice_ticket_requires_strong_secret(self) -> None:
        with pytest.raises(ValidationError, match="VOICE_TICKET_HMAC_SECRET"):
            _make_settings(
                VOICE_TICKET_ENABLED="true",
                VOICE_TICKET_HMAC_SECRET="too-short",
            )

    def test_enabled_asr_gate_requires_voice_ticket_and_independent_secret(self) -> None:
        with pytest.raises(ValidationError, match="VOICE_TICKET_ENABLED"):
            _make_settings(
                ASR_GATE_ENABLED="true",
                ASR_GATE_HMAC_SECRET="test-independent-asr-gate-secret-material-32-bytes",
            )
        with pytest.raises(ValidationError, match="independent"):
            _make_settings(
                VOICE_TICKET_ENABLED="true",
                VOICE_TICKET_HMAC_SECRET="shared-secret-material-at-least-32-bytes",
                ASR_GATE_ENABLED="true",
                ASR_GATE_HMAC_SECRET="shared-secret-material-at-least-32-bytes",
            )

    def test_enabled_speech_service_identity_requires_an_independent_secret(self) -> None:
        with pytest.raises(ValidationError, match="SPEECH_SERVICE_IDENTITY_HMAC_SECRET"):
            _make_settings(
                SPEECH_SERVICE_IDENTITY_ENABLED="true",
                SPEECH_SERVICE_IDENTITY_HMAC_SECRET="too-short",
            )
        with pytest.raises(ValidationError, match="independent"):
            _make_settings(
                SERVICE_IDENTITY_ENABLED="true",
                SERVICE_IDENTITY_HMAC_SECRET="shared-service-secret-material-at-least-32-bytes",
                SPEECH_SERVICE_IDENTITY_ENABLED="true",
                SPEECH_SERVICE_IDENTITY_HMAC_SECRET=(
                    "shared-service-secret-material-at-least-32-bytes"
                ),
            )

    @pytest.mark.parametrize("ttl", ["14", "121"])
    def test_voice_ticket_ttl_is_bounded(self, ttl: str) -> None:
        with pytest.raises(ValidationError):
            _make_settings(VOICE_TICKET_TTL_SECONDS=ttl)


# ─── Secret redaction ────────────────────────────────────────────────────────


class TestSecretRedaction:
    def test_model_dump_redacts_password(self) -> None:
        s = _make_settings(DATABASE_PASSWORD="real_password")
        dumped = s.model_dump()
        assert dumped["database_password"] == "***"

    def test_repr_redacts_password(self) -> None:
        s = _make_settings(DATABASE_PASSWORD="real_password")
        r = repr(s)
        assert "real_password" not in r
        assert "***" in r

    def test_str_redacts_password(self) -> None:
        s = _make_settings(DATABASE_PASSWORD="real_password")
        text = str(s)
        assert "real_password" not in text
        assert "***" in text

    def test_non_sensitive_fields_not_redacted(self) -> None:
        s = _make_settings()
        dumped = s.model_dump()
        assert dumped["app_title"] == "kinsun.ai Core API"
        assert dumped["docs_url"] == "/docs"
        # A service endpoint that carries no credential stays readable, so a
        # misconfigured runtime URL is still diagnosable from a dumped config.
        assert dumped["agent_runtime_url"] == "http://127.0.0.1:8001"

    def test_database_url_is_reduced_to_its_scheme(self) -> None:
        """The DSN embeds the password and host, so only the driver survives.

        This replaces an earlier expectation that database_url was a
        "non-sensitive field" returned verbatim. Field-name matching cannot see
        a credential that lives inside the value, and DATABASE_URL is exactly
        that case, so treating it as non-sensitive pinned a leak in place: any
        repr(), str() or model_dump() of Settings put the database user,
        password and host into whatever log or console received it.
        """
        s = _make_settings()
        dumped = s.model_dump()

        assert dumped["database_url"] == "postgresql+asyncpg://***"
        # The scheme is retained on purpose: it is what validate_database_url
        # rejects, so an operator debugging a refused URL still sees the driver.
        assert dumped["database_url"].startswith("postgresql+asyncpg://")

    @pytest.mark.parametrize("render", [repr, str])
    def test_database_credentials_never_appear_in_settings_output(self, render) -> None:
        s = _make_settings(
            DATABASE_URL="postgresql+asyncpg://dbuser:dbsecret@db.internal.test:5432/kinsun",
            TEST_DATABASE_URL="postgresql+asyncpg://dbuser:dbsecret@db.internal.test:5432/t",
        )

        rendered = render(s)

        assert "dbsecret" not in rendered
        assert "dbuser" not in rendered
        assert "db.internal.test" not in rendered

    def test_test_database_url_is_redacted_and_empty_stays_empty(self) -> None:
        """The disposable test DSN is a real credential too; an unset one is not."""
        configured = _make_settings(
            TEST_DATABASE_URL="postgresql+asyncpg://t:t@db.internal.test:5432/kinsun_test"
        )
        assert configured.model_dump()["test_database_url"] == "postgresql+asyncpg://***"

        unset = _make_settings()
        assert unset.model_dump()["test_database_url"] == ""

    def test_family_invitation_secret_is_redacted(self) -> None:
        secret = "test-family-invitation-secret-32-bytes"
        settings = _make_settings(FAMILY_INVITATION_HMAC_SECRET=secret)
        assert settings.model_dump()["family_invitation_hmac_secret"] == "***"
        assert secret not in repr(settings)

    def test_voice_ticket_secret_is_redacted(self) -> None:
        secret = "test-voice-ticket-secret-material-32-bytes"
        settings = _make_settings(VOICE_TICKET_HMAC_SECRET=secret)
        assert settings.model_dump()["voice_ticket_hmac_secret"] == "***"
        assert secret not in repr(settings)

    def test_asr_gate_secret_is_redacted(self) -> None:
        secret = "test-independent-asr-gate-secret-material-32-bytes"
        settings = _make_settings(ASR_GATE_HMAC_SECRET=secret)
        assert settings.model_dump()["asr_gate_hmac_secret"] == "***"
        assert secret not in repr(settings)

    def test_speech_service_identity_secret_is_redacted(self) -> None:
        secret = "speech-core-service-identity-secret-material-32-bytes"
        settings = _make_settings(SPEECH_SERVICE_IDENTITY_HMAC_SECRET=secret)
        assert settings.model_dump()["speech_service_identity_hmac_secret"] == "***"
        assert secret not in repr(settings)

    def test_google_handoff_secrets_are_redacted(self) -> None:
        identity_secret = "google-identity-secret-material-at-least-32-bytes"
        handoff_secret = "google-handoff-secret-material-at-least-32-bytes"
        settings = _make_settings(
            GOOGLE_IDENTITY_HMAC_SECRET=identity_secret,
            GOOGLE_OIDC_HANDOFF_SECRET=handoff_secret,
        )

        dumped = settings.model_dump()
        assert dumped["google_identity_hmac_secret"] == "***"
        assert dumped["google_oidc_handoff_secret"] == "***"
        assert identity_secret not in repr(settings)
        assert handoff_secret not in repr(settings)

    def test_line_handoff_secret_is_redacted(self) -> None:
        secret = "line-handoff-secret-material-at-least-32-bytes"
        settings = _make_settings(LINE_OIDC_HANDOFF_SECRET=secret)

        assert settings.model_dump()["line_oidc_handoff_secret"] == "***"
        assert secret not in repr(settings)


# ─── Singleton pattern ───────────────────────────────────────────────────────


class TestSingleton:
    def test_get_settings_returns_same_instance(self) -> None:
        get_settings.cache_clear()
        env = {"DATABASE_URL": _VALID_DB_URL, "APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=False):
            s1 = get_settings()
            s2 = get_settings()
        assert s1 is s2

    def test_get_settings_cache_clearable(self) -> None:
        """Cache can be cleared to force re-creation (useful in tests)."""
        get_settings.cache_clear()
        env = {"DATABASE_URL": _VALID_DB_URL, "APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=False):
            s1 = get_settings()
        get_settings.cache_clear()
        with patch.dict(os.environ, env, clear=False):
            s2 = get_settings()
        # Different objects after cache clear
        assert s1 is not s2


# ─── Conditional .env loading ────────────────────────────────────────────────


class TestEnvFileLoading:
    def test_development_mode_reads_env_file(self, tmp_path) -> None:
        """In development mode, .env file values are loaded."""
        env_file = tmp_path / ".env"
        env_file.write_text(f"DATABASE_URL={_VALID_DB_URL}\nDATABASE_PASSWORD=from_file\n")
        env = {"APP_ENV": "development"}
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=str(env_file))
        assert s.database_url == _VALID_DB_URL
        assert s.database_password == "from_file"

    def test_production_mode_ignores_env_file(self, tmp_path) -> None:
        """In production mode, .env file is not read (env vars only)."""
        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_PASSWORD=from_file\n")
        env = {
            "APP_ENV": "production",
            "DATABASE_URL": _VALID_DB_URL,
        }
        with patch.dict(os.environ, env, clear=True):
            # Explicitly pass _env_file=None to simulate production behavior
            s = Settings(_env_file=None)
        # Should use default, not file value
        assert s.database_password == ""

    def test_env_vars_override_env_file(self, tmp_path) -> None:
        """Environment variables take precedence over .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(f"DATABASE_URL={_VALID_DB_URL}\nPORT=3000\n")
        env = {"APP_ENV": "development", "PORT": "9999"}
        with patch.dict(os.environ, env, clear=True):
            s = Settings(_env_file=str(env_file))
        assert s.port == 9999

    def test_daily_line_notification_requires_complete_independent_secrets(self) -> None:
        with pytest.raises(ValidationError, match="LINE_ACCOUNT_LINK_ENABLED"):
            _make_settings(LINE_DAILY_NOTIFICATION_ENABLED="true")

        common = {
            "LINE_ACCOUNT_LINK_ENABLED": "true",
            "LINE_CHANNEL_SECRET": "synthetic-channel-secret",
            "LINE_CHANNEL_ACCESS_TOKEN": "synthetic-channel-token",
            "LINE_IDENTITY_HMAC_SECRET": "synthetic-identity-hmac-secret-32-bytes",
            "LINE_ACCOUNT_LINK_BASE_URL": "https://staging.example.com",
            "LINE_DAILY_NOTIFICATION_ENABLED": "true",
        }
        with pytest.raises(ValidationError, match="LINE_SUBJECT_ENCRYPTION_SECRET"):
            _make_settings(**common)

        settings = _make_settings(
            **common,
            LINE_SUBJECT_ENCRYPTION_SECRET="synthetic-independent-encryption-secret-32-bytes",
        )
        assert settings.line_daily_notification_enabled is True
        assert settings.line_daily_notification_send_time == "08:00"

    def test_daily_line_notification_rejects_non_0800_schedule(self) -> None:
        with pytest.raises(ValidationError, match="must remain 08:00"):
            _make_settings(
                LINE_ACCOUNT_LINK_ENABLED="true",
                LINE_CHANNEL_SECRET="synthetic-channel-secret",
                LINE_CHANNEL_ACCESS_TOKEN="synthetic-channel-token",
                LINE_IDENTITY_HMAC_SECRET="synthetic-identity-hmac-secret-32-bytes",
                LINE_ACCOUNT_LINK_BASE_URL="https://staging.example.com",
                LINE_DAILY_NOTIFICATION_ENABLED="true",
                LINE_SUBJECT_ENCRYPTION_SECRET=("synthetic-independent-encryption-secret-32-bytes"),
                LINE_DAILY_NOTIFICATION_SEND_TIME="09:00",
            )
