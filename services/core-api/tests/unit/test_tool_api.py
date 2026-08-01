"""HTTP-level tests for the internal Core Tool endpoint."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import tools
from app.api.error_handlers import register_exception_handlers
from app.core.exceptions import AuthorizationDeniedError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_system_service_actor
from app.middleware.auth import ActorContext, get_actor_context
from app.schemas.tool import ToolResult


def _tool_request() -> dict[str, object]:
    return {
        "tool_call_id": str(uuid4()),
        "agent_run_id": str(uuid4()),
        "tool_name": "retrieve_confirmed_memory",
        "tool_version": "1.0",
        "elder_id": str(uuid4()),
        "purpose": "LONG_TERM_MEMORY",
        "consent_version": 1,
        "policy_version": "policy-v1",
        "request_id": "tool-request-1",
        "parameters": {},
    }


def _app_for_actor(actor: ActorContext) -> FastAPI:
    app = FastAPI()
    app.include_router(tools.router)
    register_exception_handlers(app)
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_db_session] = lambda: MagicMock()
    return app


@pytest.mark.asyncio
async def test_system_service_guard_rejects_non_system_role() -> None:
    actor = ActorContext(
        actor_id=uuid4(),
        actor_role="HOME_CARE_WORKER",
        tenant_id=uuid4(),
    )

    with pytest.raises(AuthorizationDeniedError):
        await require_system_service_actor(actor)


@pytest.mark.asyncio
async def test_internal_tool_route_rejects_non_system_actor_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = ActorContext(
        actor_id=uuid4(),
        actor_role="HOME_CARE_WORKER",
        tenant_id=uuid4(),
    )
    factory = MagicMock()
    monkeypatch.setattr(tools, "ToolExecutionService", factory)

    async with AsyncClient(
        transport=ASGITransport(app=_app_for_actor(actor)),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/internal/tools/execute", json=_tool_request())

    assert response.status_code == 404
    assert response.json()["error"]["reason_code"] == "RESOURCE_NOT_FOUND_OR_FORBIDDEN"
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_internal_tool_route_allows_system_service_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = ActorContext(
        actor_id=uuid4(),
        actor_role="SYSTEM_SERVICE",
        tenant_id=uuid4(),
    )
    execute = AsyncMock(
        return_value=ToolResult(
            result_status="NO_DATA",
            trace_id="tool-trace",
        )
    )
    factory = MagicMock(return_value=SimpleNamespace(execute=execute))
    monkeypatch.setattr(tools, "ToolExecutionService", factory)

    async with AsyncClient(
        transport=ASGITransport(app=_app_for_actor(actor)),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/v1/internal/tools/execute", json=_tool_request())

    assert response.status_code == 200
    assert response.json()["data"]["result_status"] == "NO_DATA"
    execute.assert_awaited_once()
