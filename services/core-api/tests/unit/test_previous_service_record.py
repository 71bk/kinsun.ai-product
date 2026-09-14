"""History uses a new exact-visit gate and exposes only a bounded human source."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.error_handlers import register_exception_handlers
from app.api.service_records import router
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.services.service_record_service import ServiceRecordService


def values():
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    now = datetime.now(UTC)
    assignment = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        care_unit_id=uuid4(),
        status="IN_PROGRESS",
        service_start=now - timedelta(hours=1),
        service_end=now + timedelta(hours=1),
        service_scope=["assignment:read", "service_record:history:read"],
    )
    return actor, assignment


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    ["CONFIRMED", "COMPLETED", "EXPIRED", "CANCELLED", "scope", "read_scope", "time", "missing"],
)
async def test_history_denial_never_queries_notes(denial, monkeypatch):
    actor, assignment = values()
    if denial in {"scope", "read_scope"}:
        assignment.service_scope = (
            ["assignment:read"] if denial == "scope" else ["service_record:history:read"]
        )
    elif denial == "time":
        assignment.service_end = datetime.now(UTC)
    else:
        assignment.status = denial
    session = AsyncMock()
    session.scalar.return_value = None if denial == "missing" else assignment
    read = AsyncMock()
    monkeypatch.setattr(
        "app.services.service_record_service.ServiceRecordRepository.previous", read
    )
    with pytest.raises(NotFoundError):
        await ServiceRecordService(session, actor).previous(assignment.id)
    read.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["ELDER", "FAMILY_MEMBER", "DAYCARE_CARE_WORKER", "SYSTEM_SERVICE", "ADMIN"]
)
async def test_history_http_hides_role_denial(role):
    actor, assignment = values()
    actor = ActorContext(actor_id=actor.actor_id, tenant_id=actor.tenant_id, actor_role=role)
    session = AsyncMock()
    app = FastAPI()
    app.include_router(router)
    register_exception_handlers(app)
    app.dependency_overrides[require_active_actor] = lambda: actor
    app.dependency_overrides[get_db_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/home-care/assignments/{assignment.id}/previous-service-record"
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    session.scalar.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [True, False])
async def test_history_minimal_response_and_live_recheck(empty, monkeypatch):
    actor, assignment = values()
    source = SimpleNamespace(
        service_record_id=uuid4(),
        assignment_id=uuid4(),
        service_date=date(2026, 9, 13),
        service_timezone="Asia/Taipei",
        completed_at=datetime(2026, 9, 13, tzinfo=UTC),
        version=1,
        content={"note": "Synthetic human handover"},
        worker_id=uuid4(),
    )
    read = AsyncMock(return_value=None if empty else source)
    monkeypatch.setattr(
        "app.services.service_record_service.ServiceRecordRepository.previous", read
    )
    service = ServiceRecordService(AsyncMock(), actor)
    service._authorize = AsyncMock(return_value=(assignment, "UTC"))
    result = await service.previous(assignment.id)
    assert result["assignment_id"] == str(assignment.id)
    assert service._authorize.await_count == 2
    if empty:
        assert result["record"] is None
    else:
        assert set(result["record"]) == {
            "service_record_id",
            "source_assignment_id",
            "service_date",
            "service_timezone",
            "completed_at",
            "version",
            "content",
        }
        assert result["record"]["content"] == source.content["note"]
    service._authorize.side_effect = [(assignment, "UTC"), NotFoundError("Resource not found")]
    with pytest.raises(NotFoundError):
        await service.previous(assignment.id)


@pytest.mark.asyncio
async def test_history_http_empty_is_not_cached(monkeypatch):
    actor, assignment = values()
    monkeypatch.setattr(
        ServiceRecordService,
        "previous",
        AsyncMock(return_value={"assignment_id": str(assignment.id), "record": None}),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_active_actor] = lambda: actor
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/home-care/assignments/{assignment.id}/previous-service-record"
        )
    assert response.status_code == 200
    assert response.json()["data"]["record"] is None
    assert response.headers["cache-control"] == "no-store"
