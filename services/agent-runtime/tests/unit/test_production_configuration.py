"""A production start must fail closed on mock replies or ungoverned retrieval."""

from __future__ import annotations

from typing import Any

import pytest

from agent_runtime import app as app_module
from agent_runtime.app import (
    PRODUCTION_APPROVED_MODEL_PROVIDERS,
    PRODUCTION_APPROVED_RAG_MODES,
    validate_production_configuration,
)
from agent_runtime.settings import Settings

_SYNTHETIC_SECRET = "synthetic-test-service-identity-secret-32-bytes"
_SYNTHETIC_RAG_DSN = "postgresql://synthetic:synthetic@rag.invalid:5432/kinsun"


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        SERVICE_IDENTITY_ENABLED=True,
        SERVICE_IDENTITY_HMAC_SECRET=_SYNTHETIC_SECRET,
        **overrides,
    )


def test_mock_provider_is_never_an_approved_production_provider() -> None:
    """Pin the allowlist itself: adding "mock" here would silently undo the gate."""

    assert "mock" not in PRODUCTION_APPROVED_MODEL_PROVIDERS
    assert PRODUCTION_APPROVED_MODEL_PROVIDERS == {"bedrock", "gemini", "openai-compatible"}


def test_no_rag_mode_is_approved_for_production_yet() -> None:
    """Both implemented modes are staging artefacts, so the approved set is empty."""

    assert PRODUCTION_APPROVED_RAG_MODES == frozenset()


@pytest.mark.parametrize("app_env", ["local", "test", "development", "staging"])
@pytest.mark.parametrize("rag_mode", ["disabled", "staging"])
def test_non_production_profiles_keep_the_mock_and_retrieval_defaults(
    app_env: str, rag_mode: str
) -> None:
    """The suite and local runs depend on this staying a no-op."""

    validate_production_configuration(
        _settings(
            APP_ENV=app_env,
            MODEL_PROVIDER="mock",
            RAG_MODE=rag_mode,
            RAG_ALLOW_NEEDS_REVIEW_CITATIONS=True,
            RAG_STAGING_ALLOW_ALL_AUDIENCES=True,
        )
    )


def test_production_with_the_mock_provider_fails_closed() -> None:
    with pytest.raises(ValueError, match="MODEL_PROVIDER must be one of") as exc_info:
        validate_production_configuration(
            _settings(APP_ENV="production", MODEL_PROVIDER="mock", RAG_MODE="staging")
        )

    assert "bedrock, gemini, openai-compatible" in str(exc_info.value)


@pytest.mark.parametrize("model_provider", ["bedrock", "gemini", "openai-compatible"])
def test_production_with_disabled_retrieval_fails_closed(model_provider: str) -> None:
    with pytest.raises(ValueError, match="RAG_MODE has no production-approved value"):
        validate_production_configuration(
            _settings(APP_ENV="production", MODEL_PROVIDER=model_provider, RAG_MODE="disabled")
        )


def test_production_cannot_borrow_the_staging_retrieval_release() -> None:
    """A staging release is production_approved=false; production may not serve it."""

    with pytest.raises(ValueError, match="production_approved=false"):
        validate_production_configuration(
            _settings(APP_ENV="production", MODEL_PROVIDER="bedrock", RAG_MODE="staging")
        )


def test_production_reports_every_violation_from_one_failed_start() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_production_configuration(
            _settings(
                APP_ENV="production",
                MODEL_PROVIDER="mock",
                RAG_MODE="disabled",
                RAG_ALLOW_NEEDS_REVIEW_CITATIONS=True,
                RAG_STAGING_ALLOW_ALL_AUDIENCES=True,
            )
        )

    message = str(exc_info.value)
    assert "MODEL_PROVIDER must be one of" in message
    assert "RAG_MODE has no production-approved value" in message
    assert "RAG_ALLOW_NEEDS_REVIEW_CITATIONS must be false" in message
    assert "RAG_STAGING_ALLOW_ALL_AUDIENCES must be false" in message


def test_production_rejects_needs_review_citations_on_their_own() -> None:
    with pytest.raises(ValueError, match="RAG_ALLOW_NEEDS_REVIEW_CITATIONS must be false"):
        validate_production_configuration(
            _settings(
                APP_ENV="production",
                MODEL_PROVIDER="gemini",
                RAG_MODE="staging",
                RAG_ALLOW_NEEDS_REVIEW_CITATIONS=True,
            )
        )


def test_production_rejects_the_all_audiences_override_on_its_own() -> None:
    with pytest.raises(ValueError, match="RAG_STAGING_ALLOW_ALL_AUDIENCES must be false"):
        validate_production_configuration(
            _settings(
                APP_ENV="production",
                MODEL_PROVIDER="gemini",
                RAG_MODE="staging",
                RAG_STAGING_ALLOW_ALL_AUDIENCES=True,
            )
        )


@pytest.mark.parametrize("app_env", ["PRODUCTION", "  Production  ", "pRoDuCtIoN"])
def test_casing_and_padding_cannot_slip_past_the_production_gate(app_env: str) -> None:
    with pytest.raises(ValueError, match="APP_ENV=production rejected this configuration"):
        validate_production_configuration(
            _settings(APP_ENV=app_env, MODEL_PROVIDER="mock", RAG_MODE="disabled")
        )


@pytest.mark.parametrize("model_provider", ["  Bedrock ", "OPENAI_COMPATIBLE"])
def test_provider_names_are_normalized_the_same_way_the_factory_normalizes_them(
    model_provider: str,
) -> None:
    """The gate must accept exactly what ``build_provider`` accepts, no more."""

    with pytest.raises(ValueError) as exc_info:
        validate_production_configuration(
            _settings(APP_ENV="production", MODEL_PROVIDER=model_provider, RAG_MODE="staging")
        )

    assert "MODEL_PROVIDER must be one of" not in str(exc_info.value)


def test_the_failure_message_carries_no_secret_or_endpoint() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_production_configuration(
            _settings(
                APP_ENV="production",
                MODEL_PROVIDER="mock",
                RAG_MODE="disabled",
                RAG_DATABASE_URL=_SYNTHETIC_RAG_DSN,
                SERVICE_IDENTITY_REPLAY_DATABASE_URL=_SYNTHETIC_RAG_DSN,
            )
        )

    message = str(exc_info.value)
    assert _SYNTHETIC_SECRET not in message
    assert "rag.invalid" not in message
    assert "synthetic" not in message


def test_create_app_rejects_a_production_configuration_before_building_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard runs first, so no provider or replay store is constructed."""

    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("create_app built a dependency before validating the profile")

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: _settings(APP_ENV="production", MODEL_PROVIDER="mock", RAG_MODE="disabled"),
    )
    monkeypatch.setattr(app_module, "build_provider", fail_if_called)
    monkeypatch.setattr(app_module, "build_service_identity_replay_store", fail_if_called)

    with pytest.raises(ValueError, match="APP_ENV=production rejected this configuration"):
        app_module.create_app()


def test_create_app_still_builds_under_the_test_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mock/disabled default must stay startable everywhere except production."""

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: _settings(APP_ENV="test", MODEL_PROVIDER="mock", RAG_MODE="disabled"),
    )

    assert app_module.create_app() is not None
