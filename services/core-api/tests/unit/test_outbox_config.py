"""Fail-closed configuration tests for the outbox worker."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DATABASE_URL = "postgresql+asyncpg://user:pass@localhost:5432/kinsun"


def test_outbox_worker_is_disabled_by_default() -> None:
    settings = Settings(database_url=DATABASE_URL, _env_file=None)

    assert settings.outbox_worker_enabled is False
    assert settings.outbox_publisher_mode == "disabled"


def test_enabled_worker_requires_https_mode() -> None:
    with pytest.raises(ValidationError, match="OUTBOX_PUBLISHER_MODE"):
        Settings(
            database_url=DATABASE_URL,
            outbox_worker_enabled=True,
            _env_file=None,
        )


def test_https_mode_requires_fixed_url_and_long_token() -> None:
    with pytest.raises(ValidationError, match="fixed HTTPS URL"):
        Settings(
            database_url=DATABASE_URL,
            outbox_publisher_mode="https",
            outbox_publish_url="http://events.example.test/ingress",
            outbox_publish_bearer_token="x" * 32,
            _env_file=None,
        )
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        Settings(
            database_url=DATABASE_URL,
            outbox_publisher_mode="https",
            outbox_publish_url="https://events.example.test/ingress",
            outbox_publish_bearer_token="too-short",
            _env_file=None,
        )


def test_https_mode_requires_lease_longer_than_request_timeout() -> None:
    with pytest.raises(ValidationError, match="must exceed"):
        Settings(
            database_url=DATABASE_URL,
            outbox_worker_enabled=True,
            outbox_publisher_mode="https",
            outbox_publish_url="https://events.example.test/ingress",
            outbox_publish_bearer_token="x" * 32,
            outbox_publish_timeout_seconds=30,
            outbox_lease_seconds=30,
            _env_file=None,
        )
