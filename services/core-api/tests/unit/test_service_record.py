"""Service record scope, wire errors, immutable schema and replay ordering."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.api.error_handlers import register_exception_handlers
from app.api.service_records import router
from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError
from app.database_runtime_principal import RUNTIME_TABLE_PRIVILEGES
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.models.service_record import ServiceRecord
from app.schemas.service_record import CreateServiceRecordRequest
from app.services.service_record_service import ServiceRecordService


def fixture_values():
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    now = datetime.now(UTC)
    assignment = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        care_unit_id=uuid4(),
        worker_id=actor.actor_id,
        tenant_id=actor.tenant_id,
        status="IN_PROGRESS",
        version=2,
        service_start=now - timedelta(hours=1),
        service_end=now + timedelta(hours=1),
        service_scope=["assignment:read", "service_record:write", "service_record:read"],
    )
    return actor, assignment


@pytest.mark.parametrize("bad", ["", "   ", "x" * 4001])
def test_content_validation(bad):
    with pytest.raises(ValidationError):
        CreateServiceRecordRequest(expected_assignment_version=1, content=bad)


@pytest.mark.parametrize(
    "field", ["tenant_id", "elder_id", "worker_id", "service_date", "status", "version"]
)
def test_server_owned_fields_rejected(field):
    with pytest.raises(ValidationError):
        CreateServiceRecordRequest.model_validate(
            {"expected_assignment_version": 1, "content": "Synthetic note", field: "forged"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["DAYCARE_CARE_WORKER", "FAMILY_MEMBER", "ELDER", "ADMIN", "SYSTEM_SERVICE"]
)
async def test_non_home_roles_fail_closed_without_query(role):
    actor, assignment = fixture_values()
    actor = ActorContext(actor_id=actor.actor_id, tenant_id=actor.tenant_id, actor_role=role)
    session = AsyncMock()
    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[require_active_actor] = lambda: actor
    app.dependency_overrides[get_db_session] = lambda: session
    path = f"/api/v1/home-care/assignments/{assignment.id}/service-record"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for response in [
            await client.get(path),
            await client.post(
                path,
                headers={"Idempotency-Key": "synthetic"},
                json={"expected_assignment_version": 2, "content": "Synthetic note"},
            ),
        ]:
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "not_found"
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    ["missing", "CONFIRMED", "COMPLETED", "CANCELLED", "EXPIRED", "future", "expired", "scope"],
)
async def test_exact_assignment_gate_precedes_idempotency(denial, monkeypatch):
    actor, assignment = fixture_values()
    if denial in {"CONFIRMED", "COMPLETED", "CANCELLED", "EXPIRED"}:
        assignment.status = denial
    elif denial == "future":
        assignment.service_start = datetime.now(UTC) + timedelta(minutes=10)
    elif denial == "expired":
        assignment.service_end = datetime.now(UTC)
    elif denial == "scope":
        assignment.service_scope = ["assignment:read"]
    session = AsyncMock()
    session.scalar.return_value = None if denial == "missing" else assignment
    idem = MagicMock()
    monkeypatch.setattr("app.services.service_record_service.IdempotencyRepository", idem)
    with pytest.raises(NotFoundError):
        await ServiceRecordService(session, actor).create(
            assignment.id,
            CreateServiceRecordRequest(expected_assignment_version=2, content="Synthetic"),
            "key",
            "trace",
        )
    idem.assert_not_called()
    sql = str(session.scalar.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql and "worker_actor_id" in sql and "tenant_id" in sql


@pytest.mark.asyncio
async def test_live_context_filters_and_scope_without_union():
    actor, assignment = fixture_values()
    session = AsyncMock()
    session.scalar.side_effect = [assignment, None]
    with pytest.raises(NotFoundError):
        await ServiceRecordService(session, actor)._authorize(assignment.id, "service_record:write")
    sql = str(session.scalar.await_args.args[0].compile(dialect=postgresql.dialect()))
    for term in [
        "elder.tenant_id",
        "elder.status",
        "actor.status",
        "tenant.status",
        "care_unit.status",
        "actor_tenant_membership",
        "effective_to",
        "role_code",
    ]:
        assert term in sql


@pytest.mark.asyncio
async def test_replay_reauthorizes_after_claim_wait(monkeypatch):
    actor, assignment = fixture_values()
    service = ServiceRecordService(AsyncMock(), actor)
    service._authorize = AsyncMock(
        side_effect=[(assignment, "UTC"), NotFoundError("Resource not found")]
    )
    idem = SimpleNamespace(
        begin=AsyncMock(
            return_value=SimpleNamespace(replayed=True, response_body={"secret": "old"})
        )
    )
    monkeypatch.setattr(
        "app.services.service_record_service.IdempotencyRepository", lambda *args: idem
    )
    with pytest.raises(NotFoundError):
        await service.create(
            assignment.id,
            CreateServiceRecordRequest(expected_assignment_version=2, content="Synthetic"),
            "key",
            "trace",
        )
    assert service._authorize.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["version", "duplicate", "timezone"])
async def test_conflicts_do_not_write(conflict, monkeypatch):
    actor, assignment = fixture_values()
    session = AsyncMock()
    service = ServiceRecordService(session, actor)
    session.scalar.return_value = object() if conflict == "duplicate" else None
    service._authorize = AsyncMock(
        return_value=(assignment, "not/a-zone" if conflict == "timezone" else "UTC")
    )
    service._find = AsyncMock(return_value=object() if conflict == "duplicate" else None)
    idem = SimpleNamespace(begin=AsyncMock(return_value=SimpleNamespace(replayed=False)))
    monkeypatch.setattr(
        "app.services.service_record_service.IdempotencyRepository", lambda *args: idem
    )
    with pytest.raises(ConflictError):
        await service.create(
            assignment.id,
            CreateServiceRecordRequest(
                expected_assignment_version=1 if conflict == "version" else 2, content="Synthetic"
            ),
            "key",
            "trace",
        )
    session.add.assert_not_called()


def test_record_is_append_only_and_not_mutable_base_model():
    assert RUNTIME_TABLE_PRIVILEGES["service_record"] == ("SELECT", "INSERT")
    assert "updated_at" in ServiceRecord.__table__.columns
    assert ServiceRecord.__table__.c.worker_actor_id is not None
    assert ServiceRecord.__table__.c.version.nullable
    constraints = {constraint.name for constraint in ServiceRecord.__table__.constraints}
    assert "uq_service_record" in constraints
    assert "uq_service_record_single_note" in {
        index.name for index in ServiceRecord.__table__.indexes
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("timezone", ["UTC", "Asia/Taipei", "America/New_York"])
async def test_success_uses_server_scope_and_minimal_outbox(timezone, monkeypatch):
    from zoneinfo import ZoneInfo

    actor, assignment = fixture_values()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)

    async def flush():
        session.add.call_args.args[0].service_record_id = uuid4()

    session.flush = AsyncMock(side_effect=flush)
    service = ServiceRecordService(session, actor)
    service._authorize = AsyncMock(return_value=(assignment, timezone))
    service._find = AsyncMock(return_value=None)
    idem = SimpleNamespace(
        begin=AsyncMock(return_value=SimpleNamespace(replayed=False)), complete=AsyncMock()
    )
    monkeypatch.setattr(
        "app.services.service_record_service.IdempotencyRepository", lambda *args: idem
    )
    outbox = AsyncMock()
    monkeypatch.setattr("app.services.service_record_service.write_outbox_entry", outbox)
    body = await service.create(
        assignment.id,
        CreateServiceRecordRequest(expected_assignment_version=2, content="Synthetic human note"),
        "key",
        "trace",
    )
    assert body["assignment_id"] == str(assignment.id)
    assert body["worker_id"] == str(actor.actor_id)
    assert (
        body["service_date"]
        == assignment.service_start.astimezone(ZoneInfo(timezone)).date().isoformat()
    )
    assert body["content"] == "Synthetic human note"
    assert body["status"] == "COMPLETED" and body["version"] == 1
    assert assignment.status == "IN_PROGRESS" and assignment.version == 2
    assert set(outbox.await_args.kwargs["payload"]) == {
        "service_record_id",
        "assignment_id",
        "version",
        "status",
    }
    assert outbox.await_args.args[0] is session
    assert outbox.await_args.kwargs["classification"] == "RESTRICTED"
    idem.complete.assert_awaited_once()
    session.commit.assert_not_called()
