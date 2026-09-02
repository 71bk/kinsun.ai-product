"""Race, scope, expiry, and snapshot guards for idempotency claims."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.exceptions import ConflictError
from app.models.idempotency import IdempotencyRecord
from app.repositories.idempotency_repo import IdempotencyRepository

TENANT_ID = UUID("a1000000-0000-4000-8000-000000000001")
ACTOR_ID = UUID("a1000000-0000-4000-8000-000000000002")


def _repository(session: AsyncMock | None = None) -> IdempotencyRepository:
    return IdempotencyRepository(session or AsyncMock(), TENANT_ID, ACTOR_ID)


def _record(
    *,
    fingerprint: str,
    status: str = "COMPLETED",
    expires_at: datetime | None = None,
    response_body: dict | None = None,
) -> IdempotencyRecord:
    repository = _repository()
    snapshot = response_body or {"resource_id": str(uuid4()), "version": 1}
    return IdempotencyRecord(
        idempotency_key=repository.storage_key("request-1"),
        actor_id=ACTOR_ID,
        tenant_id=TENANT_ID,
        request_fingerprint=fingerprint,
        resource_type="care_action",
        resource_id=uuid4(),
        status=status,
        response_status=201,
        response_body_hash=repository.fingerprint("response", snapshot),
        response_body=snapshot,
        key_format_version=2,
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=1),
    )


def test_storage_key_is_bounded_non_reversible_and_scope_specific() -> None:
    key = "same-client-key"
    first = _repository().storage_key(key)
    other_tenant = IdempotencyRepository(AsyncMock(), uuid4(), ACTOR_ID).storage_key(key)
    other_actor = IdempotencyRepository(AsyncMock(), TENANT_ID, uuid4()).storage_key(key)

    assert first.startswith("v2:")
    assert len(first) == 67
    assert key not in first
    assert len({first, other_tenant, other_actor}) == 3


@pytest.mark.asyncio
async def test_begin_uses_atomic_insert_for_a_new_claim() -> None:
    session = AsyncMock()
    repository = _repository(session)
    session.scalar.side_effect = [None, repository.storage_key("request-1")]

    result = await repository.begin(
        key="request-1",
        operation="create_care_action",
        payload={"title": "Follow up"},
    )

    assert result.replayed is False
    insert_statement = session.scalar.await_args_list[1].args[0]
    assert "ON CONFLICT" in str(insert_statement.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_concurrent_insert_loser_replays_completed_snapshot() -> None:
    session = AsyncMock()
    repository = _repository(session)
    fingerprint = repository.fingerprint("create_care_action", {"title": "Follow up"})
    existing = _record(fingerprint=fingerprint)
    session.scalar.side_effect = [None, None, existing]

    result = await repository.begin(
        key="request-1",
        operation="create_care_action",
        payload={"title": "Follow up"},
    )

    assert result.replayed is True
    assert result.response_status == 201
    assert result.response_body == existing.response_body
    assert result.response_body is not existing.response_body


@pytest.mark.asyncio
async def test_expired_key_is_reclaimed_and_previous_snapshot_is_cleared() -> None:
    session = AsyncMock()
    repository = _repository(session)
    existing = _record(
        fingerprint="old-request",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    session.scalar.return_value = existing

    result = await repository.begin(
        key="request-1",
        operation="new-operation",
        payload={"different": True},
    )

    assert result.replayed is False
    assert existing.status == "IN_PROGRESS"
    assert existing.resource_id is None
    assert existing.response_body is None
    assert existing.response_body_hash is None
    assert existing.completed_at is None


@pytest.mark.asyncio
async def test_replay_rejects_tampered_response_snapshot() -> None:
    session = AsyncMock()
    repository = _repository(session)
    fingerprint = repository.fingerprint("operation", {"value": 1})
    existing = _record(fingerprint=fingerprint)
    existing.response_body = {"tampered": True}
    session.scalar.return_value = existing

    with pytest.raises(ConflictError, match="integrity"):
        await repository.begin(
            key="request-1",
            operation="operation",
            payload={"value": 1},
        )


@pytest.mark.asyncio
async def test_complete_persists_json_snapshot_and_completion_time() -> None:
    session = AsyncMock()
    repository = _repository(session)
    existing = _record(
        fingerprint=repository.fingerprint("operation", {"value": 1}),
        status="IN_PROGRESS",
    )
    session.scalar.return_value = existing
    resource_id = uuid4()

    await repository.complete(
        key="request-1",
        resource_type="care_action",
        resource_id=resource_id,
        response_status=201,
        response_body={"resource_id": resource_id, "created_at": datetime.now(UTC)},
    )

    assert existing.status == "COMPLETED"
    assert existing.response_body is not None
    assert existing.response_body["resource_id"] == str(resource_id)
    assert isinstance(existing.response_body["created_at"], str)
    assert existing.completed_at is not None


@pytest.mark.asyncio
async def test_complete_rejects_unbounded_response_snapshot() -> None:
    session = AsyncMock()
    repository = _repository(session)
    existing = _record(fingerprint="fingerprint", status="IN_PROGRESS")
    session.scalar.return_value = existing

    with pytest.raises(ConflictError, match="storage limit"):
        await repository.complete(
            key="request-1",
            resource_type="care_action",
            resource_id=uuid4(),
            response_status=201,
            response_body={"oversized": "x" * (256 * 1024)},
        )

    assert existing.status == "IN_PROGRESS"
    assert existing.completed_at is None


@pytest.mark.asyncio
async def test_purge_expired_is_limited_to_repository_scope() -> None:
    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(rowcount=3)
    repository = _repository(session)

    deleted = await repository.purge_expired(before=datetime.now(UTC))

    assert deleted == 3
    statement = session.execute.await_args.args[0]
    rendered = str(statement)
    assert "tenant_id" in rendered
    assert "actor_id" in rendered
    assert "expires_at" in rendered
