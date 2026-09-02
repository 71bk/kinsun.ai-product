"""Replay stores must claim atomically and stay bounded."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.adapters.service_identity_replay import InMemoryReplayStore
from app.adapters.service_identity_replay_db import DatabaseReplayStore

_CLAIM = {
    "issuer": "kinsun-test",
    "subject": "speech-gateway",
    "audience": "core-api",
    "credential_id": "00000000-0000-4000-8000-000000000001",
}


def _clock(seconds: int = 30) -> dict[str, datetime]:
    """The verification instant plus the credential expiry derived from it."""

    now = datetime.now(UTC)
    return {"now": now, "expires_at": now + timedelta(seconds=seconds)}


class _FakeTransaction:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        self._session.committed = True


class _FakeSession:
    """Records statements in order so the claim contract stays visible."""

    def __init__(self, claim_result: str | None) -> None:
        self.statements: list[tuple[str, dict[str, Any] | None]] = []
        self.committed = False
        self._claim_result = claim_result

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> None:
        self.statements.append((str(statement), params))

    async def scalar(self, statement: object, params: dict[str, Any] | None = None) -> str | None:
        self.statements.append((str(statement), params))
        return self._claim_result


def _store(session: _FakeSession) -> DatabaseReplayStore:
    return DatabaseReplayStore(lambda: (lambda: session))


async def test_in_memory_store_is_marked_non_durable_and_claims_once() -> None:
    store = InMemoryReplayStore()

    assert store.durable is False
    assert await store.claim(**_CLAIM, **_clock()) is True
    assert await store.claim(**_CLAIM, **_clock()) is False


async def test_in_memory_store_scopes_claims_by_audience() -> None:
    store = InMemoryReplayStore()

    assert await store.claim(**_CLAIM, **_clock()) is True
    other_audience = {**_CLAIM, "audience": "agent-runtime"}
    assert await store.claim(**other_audience, **_clock()) is True


async def test_database_store_claims_with_a_bounded_purge_and_commits() -> None:
    session = _FakeSession(claim_result=_CLAIM["credential_id"])

    claimed = await _store(session).claim(**_CLAIM, **_clock())

    assert claimed is True
    assert session.committed is True
    purge_sql, purge_params = session.statements[0]
    claim_sql, claim_params = session.statements[1]
    assert purge_sql.startswith("DELETE FROM service_identity.credential_nonce")
    assert "LIMIT :batch_size" in purge_sql
    assert purge_params is not None and purge_params["batch_size"] == 200
    assert "ON CONFLICT (audience, credential_id) DO NOTHING" in claim_sql
    assert claim_params == {
        "audience": "core-api",
        "credential_id": _CLAIM["credential_id"],
        "issuer": "kinsun-test",
        "subject": "speech-gateway",
        "expires_at": claim_params["expires_at"],
    }


async def test_database_store_reports_a_lost_claim_as_replay() -> None:
    session = _FakeSession(claim_result=None)

    assert await _store(session).claim(**_CLAIM, **_clock()) is False


async def test_database_store_resolves_the_session_factory_per_claim() -> None:
    """The verifier is cached for the process; the engine is not."""

    sessions = [_FakeSession(claim_result="a"), _FakeSession(claim_result=None)]
    calls = 0

    def provider():
        nonlocal calls
        session = sessions[calls]
        calls += 1
        return lambda: session

    store = DatabaseReplayStore(provider)
    assert await store.claim(**_CLAIM, **_clock()) is True
    assert await store.claim(**_CLAIM, **_clock()) is False
    assert calls == 2
