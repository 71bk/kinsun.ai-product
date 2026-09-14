"""The selected visit is the authority; elder-level fallback is never attempted."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import assignments, care_actions
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor


@pytest.fixture
def setup(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    now = datetime.now(UTC)
    visit = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        worker_id=actor.actor_id,
        tenant_id=actor.tenant_id,
        care_unit_id=uuid4(),
        status="IN_PROGRESS",
        version=2,
        service_start=now - timedelta(hours=1),
        service_end=now + timedelta(hours=1),
        service_scope=["assignment:read", "care_action:read"],
    )
    session = AsyncMock()
    session.scalar.side_effect = [visit, "Asia/Taipei", visit, "Asia/Taipei"]
    fallback = AsyncMock(side_effect=AssertionError("Unexpected elder-level authorization"))
    monkeypatch.setattr(assignments, "authorize_elder", fallback)
    monkeypatch.setattr(care_actions, "authorize_elder", fallback)
    service = SimpleNamespace(
        require_professional=MagicMock(), list_for_elder=AsyncMock(return_value=[])
    )
    monkeypatch.setattr(care_actions, "CareActionService", MagicMock(return_value=service))
    app = FastAPI()
    app.include_router(assignments.router)
    app.include_router(care_actions.router)
    register_exception_handlers(app)
    app.dependency_overrides[require_active_actor] = lambda: actor
    app.dependency_overrides[get_db_session] = lambda: session
    return app, visit, session, service


def path(visit, tasks):
    return (
        f"/api/v1/elders/{visit.elder_id}/care-actions?assignment_id={visit.id}"
        if tasks
        else f"/api/v1/home-care/assignments/{visit.id}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("tasks", [False, True])
async def test_authorized_exact_visit_is_not_cached(setup, tasks):
    app, visit, session, service = setup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path(visit, tasks))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert session.scalar.await_count == (4 if tasks else 2)
    if tasks:
        assert response.json()["data"]["items"] == []
    else:
        assert response.json()["data"]["assignment_id"] == str(visit.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("tasks", [False, True])
@pytest.mark.parametrize(
    "denial", ["missing", "read_scope", "expired", "future", "COMPLETED", "CANCELLED", "revoked"]
)
async def test_unavailable_visit_never_queries_followups(setup, tasks, denial):
    app, visit, session, service = setup
    if denial == "read_scope":
        visit.service_scope = ["care_action:read"]
    elif denial == "expired":
        visit.service_end = datetime.now(UTC)
    elif denial == "future":
        visit.service_start = datetime.now(UTC) + timedelta(hours=1)
    elif denial in {"COMPLETED", "CANCELLED"}:
        visit.status = denial
    session.scalar.side_effect = [
        None if denial == "missing" else visit,
        None if denial == "revoked" else "UTC",
    ]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path(visit, tasks))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    service.list_for_elder.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["task_scope", "CONFIRMED", "elder_mismatch"])
async def test_followups_require_started_visit_and_matching_elder(setup, denial):
    app, visit, session, service = setup
    url = path(visit, True)
    if denial == "task_scope":
        visit.service_scope = ["assignment:read"]
    elif denial == "elder_mismatch":
        url = url.replace(str(visit.elder_id), str(uuid4()))
    else:
        visit.status = denial
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(url)
    assert response.status_code == 404
    service.list_for_elder.assert_not_awaited()


@pytest.mark.asyncio
async def test_revocation_during_followup_read_discards_result(setup):
    app, visit, session, _ = setup
    session.scalar.side_effect = [visit, "UTC", NotFoundError("Resource not found")]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path(visit, True))
    assert response.status_code == 404
    assert "data" not in response.json()
