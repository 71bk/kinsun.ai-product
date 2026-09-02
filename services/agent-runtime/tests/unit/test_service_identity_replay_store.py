"""Replay protection must be durable wherever replicas can exist."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from agent_runtime.app import build_service_identity_replay_store
from agent_runtime.security.replay_store import InMemoryReplayStore, ReplayStoreError
from agent_runtime.security.replay_store_postgres import (
    PostgresReplayStore,
    build_replay_engine,
)
from agent_runtime.settings import Settings

_CLAIM = {
    "issuer": "kinsun-local",
    "subject": "core-api",
    "audience": "agent-runtime",
    "credential_id": "credential-001",
}
_SYNTHETIC_DSN = "postgresql://synthetic:synthetic@db.invalid:5432/kinsun"


def _clock(seconds: int = 30) -> dict[str, datetime]:
    """The verification instant plus the credential expiry derived from it."""

    now = datetime.now(UTC)
    return {"now": now, "expires_at": now + timedelta(seconds=seconds)}


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        SERVICE_IDENTITY_ENABLED=True,
        SERVICE_IDENTITY_HMAC_SECRET="synthetic-test-service-identity-secret-32-bytes",
        **overrides,
    )


class _FakeConnection:
    def __init__(self, claim_result: str | None, raises: bool) -> None:
        self.statements: list[tuple[str, dict[str, Any] | None]] = []
        self._claim_result = claim_result
        self._raises = raises

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> None:
        if self._raises:
            raise RuntimeError("synthetic driver failure with dsn=postgres://secret")
        self.statements.append((str(statement), params))

    async def scalar(self, statement: object, params: dict[str, Any] | None = None) -> str | None:
        self.statements.append((str(statement), params))
        return self._claim_result


class _FakeEngineTransaction:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, claim_result: str | None = "credential-001", raises: bool = False) -> None:
        self.connection = _FakeConnection(claim_result, raises)
        self.disposed = False

    def begin(self) -> _FakeEngineTransaction:
        return _FakeEngineTransaction(self.connection)

    async def dispose(self) -> None:
        self.disposed = True


async def test_in_memory_store_is_marked_non_durable_and_claims_once() -> None:
    store = InMemoryReplayStore()

    assert store.durable is False
    assert await store.claim(**_CLAIM, **_clock()) is True
    assert await store.claim(**_CLAIM, **_clock()) is False


async def test_postgres_store_claims_with_a_bounded_purge() -> None:
    engine = _FakeEngine()
    store = PostgresReplayStore(engine)  # type: ignore[arg-type]

    assert store.durable is True
    assert await store.claim(**_CLAIM, **_clock()) is True

    purge_sql, purge_params = engine.connection.statements[0]
    claim_sql, _ = engine.connection.statements[1]
    assert purge_sql.startswith("DELETE FROM service_identity.credential_nonce")
    assert purge_params is not None and purge_params["batch_size"] == 200
    assert "ON CONFLICT (audience, credential_id) DO NOTHING" in claim_sql


async def test_postgres_store_reports_a_lost_claim_as_replay() -> None:
    store = PostgresReplayStore(_FakeEngine(claim_result=None))  # type: ignore[arg-type]

    assert await store.claim(**_CLAIM, **_clock()) is False


async def test_postgres_store_failure_keeps_driver_detail_behind_the_boundary() -> None:
    store = PostgresReplayStore(_FakeEngine(raises=True))  # type: ignore[arg-type]

    with pytest.raises(ReplayStoreError) as exc_info:
        await store.claim(**_CLAIM, **_clock())

    assert "secret" not in str(exc_info.value)
    assert str(exc_info.value) == "replay claim failed: RuntimeError"


async def test_postgres_store_disposes_its_engine() -> None:
    engine = _FakeEngine()

    await PostgresReplayStore(engine).aclose()  # type: ignore[arg-type]

    assert engine.disposed is True


def test_replay_engine_normalizes_the_driver_without_connecting() -> None:
    engine = build_replay_engine(_SYNTHETIC_DSN)

    assert engine.url.drivername == "postgresql+asyncpg"


def test_local_profile_falls_back_to_the_process_local_store() -> None:
    store = build_service_identity_replay_store(_settings(APP_ENV="local"))

    assert isinstance(store, InMemoryReplayStore)
    assert store.durable is False


def test_production_without_a_durable_store_fails_closed_at_startup() -> None:
    with pytest.raises(ValueError, match="SERVICE_IDENTITY_REPLAY_DATABASE_URL"):
        build_service_identity_replay_store(_settings(APP_ENV="production"))


@pytest.mark.parametrize("configured_url", ["", "   "])
def test_production_rejects_a_blank_replay_database_url(configured_url: str) -> None:
    with pytest.raises(ValueError, match="SERVICE_IDENTITY_REPLAY_DATABASE_URL"):
        build_service_identity_replay_store(
            _settings(
                APP_ENV="production",
                SERVICE_IDENTITY_REPLAY_DATABASE_URL=configured_url,
            )
        )


async def test_configured_replay_database_url_selects_the_durable_store() -> None:
    store = build_service_identity_replay_store(
        _settings(APP_ENV="production", SERVICE_IDENTITY_REPLAY_DATABASE_URL=_SYNTHETIC_DSN)
    )

    assert isinstance(store, PostgresReplayStore)
    assert store.durable is True
    await store.aclose()
