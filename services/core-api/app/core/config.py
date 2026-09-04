"""Application configuration management.

Loads settings from environment variables (and .env file in development mode).
Provides a singleton accessor via get_settings().
"""

from __future__ import annotations

import os
import re
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.log_safety import REDACTED, redact_dsn


class AppEnv(str, Enum):
    """Application environment profiles."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class DatabasePoolMode(str, Enum):
    """Supported SQLAlchemy connection-pool strategies."""

    QUEUE = "queue"
    NULL = "null"


# Resolve the repository-level .env independently of the process working directory.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_env_file: str | None = (
    str(_REPOSITORY_ROOT / ".env") if os.getenv("APP_ENV", "development") != "production" else None
)

# Substrings in field names that indicate sensitive data (used for redaction).
_SENSITIVE_SUBSTRINGS: tuple[str, ...] = ("password", "secret", "key", "token")

# Fields whose value is a database connection string. The credential lives
# inside the value rather than in the field name, so the substring rule above
# can never reach it — these are redacted by shape instead. Only the database
# DSNs qualify: the other URL settings carry no credential, and blanket-matching
# "url" would blind operators to misconfigured service endpoints.
_DSN_FIELD_NAMES: frozenset[str] = frozenset({"database_url", "test_database_url"})


class Settings(BaseSettings):
    """Central application settings.

    All values come from environment variables. In development mode a .env file
    is also read (env vars take precedence over .env values).
    """

    model_config = SettingsConfigDict(
        env_file=_env_file,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Application ─────────────────────────────────────────────────────────────
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_title: str = "kinsun.ai Core API"
    app_version: str = "0.1.0"
    docs_url: str = "/docs"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)

    # ─── Database ────────────────────────────────────────────────────────────────
    # The DSN embeds the database user, password and host, so it is redacted by
    # shape in _redacted_dict() — repr(), str() and model_dump() stay safe to log.
    database_url: str  # Required — validated below
    db_pool_mode: DatabasePoolMode = DatabasePoolMode.QUEUE
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_connect_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    db_recovery_timeout_seconds: float = Field(default=10.0, gt=0, le=60)

    # ─── Testing ─────────────────────────────────────────────────────────────────
    test_database_url: str = ""

    # ─── Secrets (redacted in output) ────────────────────────────────────────────
    database_password: str = ""

    # ─── Authentication ──────────────────────────────────────────────────────────
    fake_auth_enabled: bool = False
    fake_auth_actor_id: UUID | None = None
    fake_auth_tenant_id: UUID | None = None
    fake_auth_actor_role: str = Field(default="ELDER", min_length=1, max_length=64)
    family_invitation_hmac_secret: str = ""
    google_oidc_client_id: str = Field(default="", max_length=512)
    google_oidc_jwks_cache_seconds: int = Field(default=300, ge=30, le=3_600)
    google_oidc_http_timeout_seconds: float = Field(default=5.0, gt=0, le=15)
    google_identity_hmac_secret: str = ""
    google_identity_hmac_key_version: int = Field(default=1, ge=1, le=2_147_483_647)
    google_oidc_handoff_secret: str = ""
    google_pending_identity_ttl_seconds: int = Field(default=600, ge=60, le=900)
    google_oidc_handoff_enabled: bool = False

    # Kinsun-owned email verification. The first delivery adapter is strictly
    # development-only; production remains unavailable until real email
    # delivery is implemented and selected explicitly.
    kinsun_native_auth_enabled: bool = False
    kinsun_identity_hmac_secret: str = ""
    kinsun_identity_hmac_key_version: int = Field(default=1, ge=1, le=2_147_483_647)
    kinsun_email_challenge_hmac_secret: str = ""
    kinsun_auth_handoff_secret: str = ""
    kinsun_email_delivery_mode: str = Field(default="disabled", max_length=32)
    kinsun_synthetic_email_code_secret: str = ""
    kinsun_email_challenge_ttl_seconds: int = Field(default=600, ge=120, le=900)
    kinsun_email_challenge_max_attempts: int = Field(default=5, ge=1, le=5)
    kinsun_password_parameter_version: int = Field(default=1, ge=1, le=2_147_483_647)
    kinsun_password_memory_cost_kib: int = Field(default=65_536, ge=8_192, le=1_048_576)
    kinsun_password_iterations: int = Field(default=3, ge=1, le=10)
    kinsun_password_lanes: int = Field(default=4, ge=1, le=16)
    kinsun_password_max_attempts: int = Field(default=5, ge=3, le=20)
    kinsun_password_lockout_seconds: int = Field(default=900, ge=30, le=86_400)

    # Provider-neutral Core-owned browser sessions. The authenticator remains
    # fail-closed until this explicit rollout gate is enabled.
    app_session_auth_enabled: bool = False
    app_session_elder_family_idle_ttl_seconds: int = Field(
        default=604_800,
        ge=300,
        le=7_776_000,
    )
    app_session_elder_family_absolute_ttl_seconds: int = Field(
        default=2_592_000,
        ge=300,
        le=31_536_000,
    )
    app_session_workforce_idle_ttl_seconds: int = Field(
        default=28_800,
        ge=300,
        le=604_800,
    )
    app_session_workforce_absolute_ttl_seconds: int = Field(
        default=86_400,
        ge=300,
        le=2_592_000,
    )
    app_session_touch_interval_seconds: int = Field(default=300, ge=30, le=3_600)
    app_session_recent_auth_window_seconds: int = Field(default=600, ge=60, le=3_600)
    app_session_max_active_per_actor: int = Field(default=5, ge=1, le=20)

    # Non-production first slice for staff-created, accountless Elder tablet
    # handoff. These remain independent from normal actor App Sessions.
    assisted_elder_sessions_enabled: bool = False
    assisted_elder_pairing_ttl_seconds: int = Field(default=600, ge=60, le=1_800)
    assisted_elder_idle_ttl_seconds: int = Field(default=1_800, ge=300, le=14_400)
    assisted_elder_absolute_ttl_seconds: int = Field(default=28_800, ge=300, le=86_400)
    assisted_elder_acknowledgement_policy_version: str = Field(
        default="demo-consent-v1",
        min_length=1,
        max_length=40,
    )
    care_profile_ai_context_enabled: bool = False

    # ─── LINE Messaging API (disabled until routes and provider are approved) ─────
    line_channel_secret: str = ""
    line_channel_access_token: str = ""
    line_account_link_enabled: bool = False
    line_identity_hmac_secret: str = ""
    line_identity_hmac_key_version: int = Field(default=1, ge=1, le=2_147_483_647)
    line_login_channel_id: str = Field(default="", max_length=32)
    line_oidc_http_timeout_seconds: float = Field(default=5.0, gt=0, le=15)
    line_oidc_handoff_secret: str = ""
    line_pending_identity_ttl_seconds: int = Field(default=600, ge=60, le=900)
    line_account_merge_ttl_seconds: int = Field(default=600, ge=60, le=900)
    line_oidc_handoff_enabled: bool = False
    line_account_link_base_url: str = Field(default="", max_length=2048)
    line_link_challenge_ttl_seconds: int = Field(default=600, ge=60, le=600)
    line_link_challenge_max_attempts: int = Field(default=3, ge=1, le=5)
    line_messaging_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    line_subject_encryption_secret: str = ""
    line_daily_notification_enabled: bool = False
    line_daily_notification_timezone: str = Field(default="Asia/Taipei", max_length=64)
    line_daily_notification_send_time: str = Field(default="08:00", max_length=5)

    # Provider-neutral outbox delivery. The HTTPS endpoint is expected to be a
    # durable event ingress selected by the deployment owner; rollout is off by
    # default and cannot start with a partial credential/configuration set.
    outbox_worker_enabled: bool = False
    outbox_publisher_mode: str = Field(default="disabled", max_length=16)
    outbox_publish_url: str = Field(default="", max_length=2048)
    outbox_publish_bearer_token: str = ""
    outbox_publish_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    outbox_poll_interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
    outbox_batch_size: int = Field(default=50, ge=1, le=500)
    outbox_lease_seconds: int = Field(default=30, ge=5, le=3_600)
    outbox_max_attempts: int = Field(default=10, ge=1, le=100)
    outbox_retry_base_seconds: int = Field(default=2, ge=1, le=3_600)
    outbox_retry_max_seconds: int = Field(default=300, ge=1, le=86_400)

    # ─── Internal service adapters ───────────────────────────────────────────────
    voice_ticket_enabled: bool = False
    voice_ticket_hmac_secret: str = ""
    voice_ticket_ttl_seconds: int = Field(default=60, ge=15, le=120)
    speech_synthesis_capability_enabled: bool = False
    speech_synthesis_capability_hmac_secret: str = ""
    speech_synthesis_capability_ttl_seconds: int = Field(default=60, ge=15, le=120)
    speech_synthesis_quota_window_seconds: int = Field(default=60, ge=10, le=3600)
    speech_synthesis_client_request_limit: int = Field(default=30, ge=1, le=10_000)
    speech_synthesis_client_character_limit: int = Field(default=30_000, ge=1, le=10_000_000)
    speech_synthesis_actor_request_limit: int = Field(default=20, ge=1, le=10_000)
    speech_synthesis_actor_character_limit: int = Field(default=20_000, ge=1, le=10_000_000)
    speech_synthesis_tenant_request_limit: int = Field(default=100, ge=1, le=100_000)
    speech_synthesis_tenant_character_limit: int = Field(default=100_000, ge=1, le=100_000_000)
    asr_gate_enabled: bool = False
    asr_gate_hmac_secret: str = ""
    asr_gate_confidence_threshold: float = Field(default=0.85, gt=0, le=1)
    asr_gate_evidence_ttl_seconds: int = Field(default=900, ge=60, le=86_400)
    agent_runtime_url: str = "http://127.0.0.1:8001"
    agent_runtime_timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    agent_runtime_model_id: str = Field(default="mock", min_length=1, max_length=200)
    service_identity_enabled: bool = False
    service_identity_hmac_secret: str = ""
    service_identity_issuer: str = Field(default="kinsun-local", min_length=1, max_length=80)
    service_identity_ttl_seconds: int = Field(default=30, ge=1, le=60)
    speech_service_identity_enabled: bool = False
    speech_service_identity_hmac_secret: str = ""
    speech_service_identity_issuer: str = Field(
        default="kinsun-local",
        min_length=1,
        max_length=80,
    )
    speech_service_identity_ttl_seconds: int = Field(default=30, ge=1, le=60)

    # Evidence-aware Memory is an explicit rollout. Both gates default off so a
    # new runtime revision cannot silently activate or retrieve long-term
    # memories merely because the expanded schema already exists.
    evidence_aware_memory: bool = False
    auto_low_risk_memory: bool = False

    # ─── Validators ──────────────────────────────────────────────────────────────

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg:// scheme")
        return v

    @model_validator(mode="after")
    def validate_service_configuration(self) -> Settings:
        """Require complete server-owned auth and LINE settings when enabled."""
        session_lifetimes = (
            (
                "elder/family",
                self.app_session_elder_family_idle_ttl_seconds,
                self.app_session_elder_family_absolute_ttl_seconds,
            ),
            (
                "workforce",
                self.app_session_workforce_idle_ttl_seconds,
                self.app_session_workforce_absolute_ttl_seconds,
            ),
        )
        for label, idle_seconds, absolute_seconds in session_lifetimes:
            if idle_seconds > absolute_seconds:
                raise ValueError(f"App Session {label} idle TTL must not exceed its absolute TTL")
            if self.app_session_touch_interval_seconds >= idle_seconds:
                raise ValueError(
                    f"APP_SESSION_TOUCH_INTERVAL_SECONDS must be shorter than the {label} "
                    "idle TTL"
                )

        if self.assisted_elder_idle_ttl_seconds > self.assisted_elder_absolute_ttl_seconds:
            raise ValueError("Assisted Elder Session idle TTL must not exceed its absolute TTL")
        if self.app_env == AppEnv.PRODUCTION and (
            self.assisted_elder_sessions_enabled or self.care_profile_ai_context_enabled
        ):
            raise ValueError(
                "Assisted Elder Session and Care Profile AI context are non-production only"
            )

        if self.google_identity_hmac_key_version != 1:
            raise ValueError(
                "GOOGLE_IDENTITY_HMAC_KEY_VERSION must remain 1; "
                "rotation requires an explicit identity rekey migration"
            )
        if self.kinsun_identity_hmac_key_version != 1:
            raise ValueError(
                "KINSUN_IDENTITY_HMAC_KEY_VERSION must remain 1; "
                "rotation requires an explicit identity rekey migration"
            )
        if self.kinsun_email_delivery_mode not in {"disabled", "synthetic"}:
            raise ValueError("KINSUN_EMAIL_DELIVERY_MODE must be either disabled or synthetic")
        if self.kinsun_native_auth_enabled:
            if not self.app_session_auth_enabled:
                raise ValueError(
                    "APP_SESSION_AUTH_ENABLED must be true when " "KINSUN_NATIVE_AUTH_ENABLED=true"
                )
            if self.kinsun_email_delivery_mode != "synthetic":
                raise ValueError(
                    "Kinsun native auth has no approved production email adapter; "
                    "development must select synthetic delivery explicitly"
                )
            if self.app_env == AppEnv.PRODUCTION:
                raise ValueError("Synthetic Kinsun email delivery is forbidden in production")
            if not re.fullmatch(r"[0-9]{6}", self.kinsun_synthetic_email_code_secret):
                raise ValueError(
                    "KINSUN_SYNTHETIC_EMAIL_CODE_SECRET must contain exactly six digits"
                )
            kinsun_secrets = {
                self.kinsun_identity_hmac_secret,
                self.kinsun_email_challenge_hmac_secret,
                self.kinsun_auth_handoff_secret,
                self.family_invitation_hmac_secret,
            }
            if any(len(secret.encode("utf-8")) < 32 for secret in kinsun_secrets):
                raise ValueError(
                    "Kinsun identity, challenge, handoff, and family invitation secrets "
                    "must each contain at least 32 bytes"
                )
            if len(kinsun_secrets) != 4:
                raise ValueError("Kinsun authentication secrets must be independent")
            if self.kinsun_password_parameter_version != 1:
                raise ValueError(
                    "KINSUN_PASSWORD_PARAMETER_VERSION must remain 1; "
                    "a change requires an explicit credential rehash rollout"
                )
        if (
            self.google_identity_hmac_secret
            and self.google_oidc_handoff_secret
            and self.google_identity_hmac_secret == self.google_oidc_handoff_secret
        ):
            raise ValueError(
                "GOOGLE_IDENTITY_HMAC_SECRET and GOOGLE_OIDC_HANDOFF_SECRET " "must be independent"
            )
        if self.google_oidc_handoff_enabled:
            if not self.app_session_auth_enabled:
                raise ValueError(
                    "APP_SESSION_AUTH_ENABLED must be true when " "GOOGLE_OIDC_HANDOFF_ENABLED=true"
                )
            if not self.google_oidc_client_id.strip():
                raise ValueError(
                    "GOOGLE_OIDC_CLIENT_ID is required when " "GOOGLE_OIDC_HANDOFF_ENABLED=true"
                )
            if len(self.google_identity_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "GOOGLE_IDENTITY_HMAC_SECRET must contain at least 32 bytes when "
                    "GOOGLE_OIDC_HANDOFF_ENABLED=true"
                )
            if len(self.google_oidc_handoff_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "GOOGLE_OIDC_HANDOFF_SECRET must contain at least 32 bytes when "
                    "GOOGLE_OIDC_HANDOFF_ENABLED=true"
                )
            if len(self.family_invitation_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "FAMILY_INVITATION_HMAC_SECRET must contain at least 32 bytes when "
                    "GOOGLE_OIDC_HANDOFF_ENABLED=true"
                )
            if (
                len(
                    {
                        self.google_identity_hmac_secret,
                        self.google_oidc_handoff_secret,
                        self.family_invitation_hmac_secret,
                    }
                )
                != 3
            ):
                raise ValueError(
                    "Google identity, Google handoff, and family invitation secrets "
                    "must be independent"
                )

        if self.line_account_link_enabled:
            if not self.line_channel_secret.strip() or not self.line_channel_access_token.strip():
                raise ValueError(
                    "LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN are required "
                    "when LINE_ACCOUNT_LINK_ENABLED=true"
                )
            base_url = self.line_account_link_base_url.strip().rstrip("/")
            authority = base_url.removeprefix("https://")
            if (
                not base_url.startswith("https://")
                or not authority
                or "/" in authority
                or "@" in authority
                or "?" in authority
                or "#" in authority
                or any(character.isspace() for character in authority)
            ):
                raise ValueError(
                    "LINE_ACCOUNT_LINK_BASE_URL must be a fixed HTTPS origin "
                    "when LINE_ACCOUNT_LINK_ENABLED=true"
                )
            self.line_account_link_base_url = base_url
        if self.line_account_link_enabled or self.line_oidc_handoff_enabled:
            if len(self.line_identity_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "LINE_IDENTITY_HMAC_SECRET must contain at least 32 bytes when "
                    "a LINE identity flow is enabled"
                )
            if self.line_identity_hmac_key_version != 1:
                raise ValueError(
                    "LINE_IDENTITY_HMAC_KEY_VERSION must remain 1 for the MVP; "
                    "key rotation requires an explicit identity rekey migration"
                )
        if self.line_oidc_handoff_enabled:
            if not self.app_session_auth_enabled:
                raise ValueError(
                    "APP_SESSION_AUTH_ENABLED must be true when " "LINE_OIDC_HANDOFF_ENABLED=true"
                )
            if not re.fullmatch(r"[0-9]{5,32}", self.line_login_channel_id):
                raise ValueError(
                    "LINE_LOGIN_CHANNEL_ID is required when " "LINE_OIDC_HANDOFF_ENABLED=true"
                )
            if len(self.line_oidc_handoff_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "LINE_OIDC_HANDOFF_SECRET must contain at least 32 bytes when "
                    "LINE_OIDC_HANDOFF_ENABLED=true"
                )
            if len(self.family_invitation_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "FAMILY_INVITATION_HMAC_SECRET must contain at least 32 bytes when "
                    "LINE_OIDC_HANDOFF_ENABLED=true"
                )
            line_secrets = {
                self.line_identity_hmac_secret,
                self.line_oidc_handoff_secret,
                self.family_invitation_hmac_secret,
            }
            if len(line_secrets) != 3 or self.line_oidc_handoff_secret in {
                self.line_channel_secret,
                self.google_oidc_handoff_secret,
            }:
                raise ValueError(
                    "LINE identity, LINE handoff, and family invitation secrets "
                    "must be independent"
                )
        if self.line_daily_notification_enabled:
            if not self.line_account_link_enabled:
                raise ValueError(
                    "LINE_ACCOUNT_LINK_ENABLED must be true when "
                    "LINE_DAILY_NOTIFICATION_ENABLED=true"
                )
            if len(self.line_subject_encryption_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "LINE_SUBJECT_ENCRYPTION_SECRET must contain at least 32 bytes "
                    "when LINE_DAILY_NOTIFICATION_ENABLED=true"
                )
            if self.line_subject_encryption_secret in {
                self.line_channel_secret,
                self.line_identity_hmac_secret,
                self.family_invitation_hmac_secret,
            }:
                raise ValueError(
                    "LINE_SUBJECT_ENCRYPTION_SECRET must be independent from all other secrets"
                )
            if self.line_daily_notification_timezone != "Asia/Taipei":
                raise ValueError("LINE_DAILY_NOTIFICATION_TIMEZONE must be Asia/Taipei")
            if not re.fullmatch(
                r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",
                self.line_daily_notification_send_time,
            ):
                raise ValueError("LINE_DAILY_NOTIFICATION_SEND_TIME must use HH:MM")
            if self.line_daily_notification_send_time != "08:00":
                raise ValueError("LINE_DAILY_NOTIFICATION_SEND_TIME must remain 08:00")
        if self.outbox_publisher_mode not in {"disabled", "https"}:
            raise ValueError("OUTBOX_PUBLISHER_MODE must be either disabled or https")
        if self.outbox_worker_enabled and self.outbox_publisher_mode != "https":
            raise ValueError("OUTBOX_PUBLISHER_MODE must be https when OUTBOX_WORKER_ENABLED=true")
        if self.outbox_publisher_mode == "https":
            publish_url = self.outbox_publish_url.strip()
            parsed = urlsplit(publish_url)
            try:
                parsed_port = parsed.port
            except ValueError as exc:
                raise ValueError("OUTBOX_PUBLISH_URL has an invalid port") from exc
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or any(character.isspace() for character in publish_url)
                or parsed_port == 0
            ):
                raise ValueError(
                    "OUTBOX_PUBLISH_URL must be a fixed HTTPS URL without credentials, "
                    "query, or fragment"
                )
            self.outbox_publish_url = publish_url
            if len(self.outbox_publish_bearer_token.encode("utf-8")) < 32:
                raise ValueError(
                    "OUTBOX_PUBLISH_BEARER_TOKEN must contain at least 32 bytes "
                    "when HTTPS publishing is selected"
                )
            if self.outbox_lease_seconds <= self.outbox_publish_timeout_seconds:
                raise ValueError("OUTBOX_LEASE_SECONDS must exceed OUTBOX_PUBLISH_TIMEOUT_SECONDS")
        if self.outbox_retry_max_seconds < self.outbox_retry_base_seconds:
            raise ValueError(
                "OUTBOX_RETRY_MAX_SECONDS must be greater than or equal to "
                "OUTBOX_RETRY_BASE_SECONDS"
            )
        if self.voice_ticket_enabled and len(self.voice_ticket_hmac_secret.encode("utf-8")) < 32:
            raise ValueError(
                "VOICE_TICKET_HMAC_SECRET must contain at least 32 bytes "
                "when VOICE_TICKET_ENABLED=true"
            )
        if self.speech_synthesis_capability_enabled:
            if len(self.speech_synthesis_capability_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "SPEECH_SYNTHESIS_CAPABILITY_HMAC_SECRET must contain at least 32 bytes "
                    "when SPEECH_SYNTHESIS_CAPABILITY_ENABLED=true"
                )
            if not self.speech_service_identity_enabled:
                raise ValueError(
                    "SPEECH_SERVICE_IDENTITY_ENABLED must be true when "
                    "SPEECH_SYNTHESIS_CAPABILITY_ENABLED=true"
                )
            if self.speech_synthesis_capability_hmac_secret in {
                self.voice_ticket_hmac_secret,
                self.asr_gate_hmac_secret,
                self.service_identity_hmac_secret,
                self.speech_service_identity_hmac_secret,
                self.google_oidc_handoff_secret,
                self.line_oidc_handoff_secret,
            }:
                raise ValueError(
                    "SPEECH_SYNTHESIS_CAPABILITY_HMAC_SECRET must be independent from "
                    "other secrets"
                )
        if self.asr_gate_enabled:
            if not self.voice_ticket_enabled:
                raise ValueError("VOICE_TICKET_ENABLED must be true when ASR_GATE_ENABLED=true")
            if len(self.asr_gate_hmac_secret.encode("utf-8")) < 32:
                raise ValueError("ASR_GATE_HMAC_SECRET must contain at least 32 bytes when enabled")
            if self.asr_gate_hmac_secret == self.voice_ticket_hmac_secret:
                raise ValueError(
                    "ASR_GATE_HMAC_SECRET must be independent from " "VOICE_TICKET_HMAC_SECRET"
                )
        if self.service_identity_enabled:
            if len(self.service_identity_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "SERVICE_IDENTITY_HMAC_SECRET must contain at least 32 bytes when enabled"
                )
            if self.service_identity_hmac_secret in {
                self.voice_ticket_hmac_secret,
                self.asr_gate_hmac_secret,
                self.google_oidc_handoff_secret,
                self.line_oidc_handoff_secret,
            }:
                raise ValueError(
                    "SERVICE_IDENTITY_HMAC_SECRET must be independent from other secrets"
                )
        if self.speech_service_identity_enabled:
            if len(self.speech_service_identity_hmac_secret.encode("utf-8")) < 32:
                raise ValueError(
                    "SPEECH_SERVICE_IDENTITY_HMAC_SECRET must contain at least 32 bytes "
                    "when enabled"
                )
            if self.speech_service_identity_hmac_secret in {
                self.service_identity_hmac_secret,
                self.voice_ticket_hmac_secret,
                self.asr_gate_hmac_secret,
                self.google_oidc_handoff_secret,
                self.line_oidc_handoff_secret,
            }:
                raise ValueError(
                    "SPEECH_SERVICE_IDENTITY_HMAC_SECRET must be independent from other secrets"
                )
        if self.auto_low_risk_memory and not self.evidence_aware_memory:
            raise ValueError("EVIDENCE_AWARE_MEMORY must be true when AUTO_LOW_RISK_MEMORY=true")
        return self

    # ─── Secret redaction ────────────────────────────────────────────────────────

    @staticmethod
    def _is_sensitive(field_name: str) -> bool:
        """Return True if the field name contains a sensitive substring."""
        lower = field_name.lower()
        return any(sub in lower for sub in _SENSITIVE_SUBSTRINGS)

    def _redacted_dict(self, **kwargs: Any) -> dict[str, Any]:
        """Return model data with sensitive fields replaced or reduced."""
        data = super().model_dump(**kwargs)
        for field_name, value in data.items():
            if self._is_sensitive(field_name):
                data[field_name] = REDACTED
            elif field_name in _DSN_FIELD_NAMES and isinstance(value, str):
                # Keep the scheme so a rejected driver is still diagnosable;
                # drop the authority, which carries the password and host.
                data[field_name] = redact_dsn(value)
        return data

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to redact sensitive fields."""
        return self._redacted_dict(**kwargs)

    def __repr__(self) -> str:
        redacted = self._redacted_dict()
        pairs = ", ".join(f"{k}={v!r}" for k, v in redacted.items())
        return f"Settings({pairs})"

    def __str__(self) -> str:
        return self.__repr__()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance.

    Uses @lru_cache so the same object is returned on every call within the
    process lifetime.
    """
    return Settings()
