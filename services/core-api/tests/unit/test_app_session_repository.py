"""Query-shape tests for App Session persistence boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.actor import Actor
from app.models.app_session import AppSession
from app.models.line_identity import ExternalIdentity
from app.repositories.app_session_repo import AppSessionRepository

_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class _OneResult:
    def __init__(self, row: object | None) -> None:
        self._row = row

    def one_or_none(self) -> object | None:
        return self._row


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _ManyResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


def _models() -> tuple[ExternalIdentity, Actor, AppSession]:
    actor = Actor(actor_type="ELDER", display_name="Test", status="ACTIVE")
    actor.id = uuid4()
    identity = ExternalIdentity(
        provider="GOOGLE",
        external_subject_digest="a" * 64,
        digest_key_version=1,
        actor_id=actor.id,
        status="ACTIVE",
    )
    identity.id = uuid4()
    app_session = AppSession(
        token_digest="b" * 64,
        actor_id=actor.id,
        external_identity_id=identity.id,
        status="ACTIVE",
        authenticated_at=_NOW,
        last_seen_at=_NOW,
        idle_expires_at=_NOW + timedelta(days=7),
        absolute_expires_at=_NOW + timedelta(days=30),
        version=1,
    )
    app_session.id = uuid4()
    return identity, actor, app_session


@pytest.mark.asyncio
async def test_active_identity_query_locks_and_requires_live_identity_and_actor() -> None:
    identity, actor, _ = _models()
    session = AsyncMock()
    session.execute.return_value = _OneResult((identity, actor))

    resolved = await AppSessionRepository(session).get_active_identity(
        identity.id,
        for_update=True,
    )

    assert resolved is not None
    assert resolved.identity is identity
    assert resolved.actor is actor
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "external_identity.status = 'ACTIVE'" in sql
    assert "actor.status = 'ACTIVE'" in sql
    assert "FOR UPDATE" in sql


@pytest.mark.asyncio
async def test_digest_query_returns_current_session_identity_and_actor_without_status_filter() -> (
    None
):
    identity, actor, app_session = _models()
    session = AsyncMock()
    session.execute.return_value = _OneResult((app_session, identity, actor))

    resolved = await AppSessionRepository(session).get_by_digest("b" * 64)

    assert resolved is not None
    assert resolved.app_session is app_session
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "app_session.token_digest" in sql
    assert "external_identity" in sql
    assert "JOIN eldercare_ai.actor" in sql
    assert "status = 'ACTIVE'" not in sql


@pytest.mark.asyncio
async def test_expired_cleanup_is_scoped_to_actor_and_increments_version() -> None:
    _, actor, _ = _models()
    session = AsyncMock()

    await AppSessionRepository(session).revoke_expired_for_actor(actor_id=actor.id, now=_NOW)

    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "app_session.actor_id" in sql
    assert "app_session.status = 'ACTIVE'" in sql
    assert "app_session.idle_expires_at <=" in sql
    assert "app_session.absolute_expires_at <=" in sql
    assert "version=(eldercare_ai.app_session.version + 1)" in sql


@pytest.mark.asyncio
async def test_live_session_cap_query_excludes_time_expired_rows_and_locks() -> None:
    _, actor, app_session = _models()
    session = AsyncMock()
    session.execute.return_value = _ManyResult([app_session])

    rows = await AppSessionRepository(session).list_live_for_actor(
        actor_id=actor.id,
        now=_NOW,
        for_update=True,
    )

    assert rows == [app_session]
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "app_session.idle_expires_at >" in sql
    assert "app_session.absolute_expires_at >" in sql
    assert "ORDER BY eldercare_ai.app_session.authenticated_at DESC" in sql
    assert "FOR UPDATE" in sql
