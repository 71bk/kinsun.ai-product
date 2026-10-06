"""Synthetic professional access and fixed public-audience regression tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.adapters.agent_runtime import get_agent_runtime_client
from app.api import family_knowledge, staff_knowledge
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.core.exceptions import AuthenticationError
from app.middleware.auth import get_actor_context
from app.schemas.public_knowledge import PublicKnowledgeAnswer


@pytest.fixture
def boundary(monkeypatch):
    app = FastAPI()
    app.include_router(staff_knowledge.router)
    app.include_router(family_knowledge.router)
    register_exception_handlers(app)
    upstream = SimpleNamespace(
        retrieve_public_knowledge=AsyncMock(
            return_value=PublicKnowledgeAnswer(status="NO_DATA", answer="Synthetic fallback")
        )
    )
    app.dependency_overrides[get_agent_runtime_client] = lambda: upstream
    settings = SimpleNamespace(app_env="test", knowledge_router_v2_enabled=True)
    for api in (staff_knowledge, family_knowledge):
        monkeypatch.setattr(api, "get_settings", lambda: settings)
    return app, upstream, settings


def actor(app, role, status="ACTIVE"):
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id=uuid4(), tenant_id=uuid4(), actor_role=role, status=status
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["HOME_CARE_WORKER", "DAYCARE_CARE_WORKER", "FAMILY_MEMBER", "ELDER", "ADMIN"]
)
@pytest.mark.parametrize("surface", ["staff", "family"])
async def test_roles_cannot_cross_public_audiences(boundary, role, surface):
    app, upstream, _ = boundary
    actor(app, role)
    allowed = role in (
        {"HOME_CARE_WORKER", "DAYCARE_CARE_WORKER"} if surface == "staff" else {"FAMILY_MEMBER"}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/{surface}/knowledge/questions", json={"question": "長照法第二條"}
        )
    assert response.status_code == (200 if allowed else 404)
    if not allowed:
        upstream.retrieve_public_knowledge.assert_not_called()
        return
    payload = upstream.retrieve_public_knowledge.call_args.kwargs["request_payload"]
    assert payload["audience"] == (
        "care_professional" if surface == "staff" else "family_caregiver"
    )
    assert payload["purpose"] == "legal_reference"
    assert payload["query_profile"] == "legal"
    assert not {"elder_id", "tenant_id", "actor_id", "session_id"}.intersection(payload)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,expected",
    [
        ("anonymous", 401),
        ("suspended", 403),
        ("production", 503),
        ("disabled", 503),
        ("forged_scope", 422),
        ("private", 200),
        ("declined", 200),
    ],
)
async def test_rejections_never_call_the_private_service(boundary, case, expected):
    app, upstream, settings = boundary
    actor(app, "HOME_CARE_WORKER", "SUSPENDED" if case == "suspended" else "ACTIVE")
    if case == "anonymous":

        async def anonymous():
            raise AuthenticationError("Authentication required")

        app.dependency_overrides[get_actor_context] = anonymous
    if case == "production":
        settings.app_env = "production"
    if case == "disabled":
        settings.knowledge_router_v2_enabled = False
    body = {"question": "申請長照服務"}
    if case == "forged_scope":
        body.update(audience="system_admin", elder_id="private-value")
    if case == "private":
        body["question"] = "其他個案的病歷紀錄"
    if case == "declined":
        body["question"] = "不用查資料"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/staff/knowledge/questions", json=body)
    assert response.status_code == expected
    assert "private-value" not in response.text
    upstream.retrieve_public_knowledge.assert_not_called()


@pytest.mark.asyncio
async def test_general_information_does_not_require_an_elder_or_assignment(boundary):
    app, upstream, _ = boundary
    actor(app, "DAYCARE_CARE_WORKER")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/staff/knowledge/questions",
            json={"question": "如何申請長照服務？", "language": "en-US"},
        )
    assert response.status_code == 200
    payload = upstream.retrieve_public_knowledge.call_args.kwargs["request_payload"]
    assert payload["purpose"] == "general_information"
    assert payload["language"] == "en-US"
