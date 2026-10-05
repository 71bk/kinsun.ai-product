"""Synthetic, no-DB family authorization and private evidence boundary tests."""

import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.adapters.agent_runtime import AgentRuntimeClient, get_agent_runtime_client
from app.adapters.public_knowledge import public_answer
from app.adapters.service_identity import SERVICE_CREDENTIAL_HEADER, ServiceCredentialSigner
from app.api import family_knowledge as api
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.core.exceptions import AuthenticationError
from app.middleware.auth import get_actor_context
from app.schemas.family_knowledge import FamilyKnowledgeAnswer

ROOT = Path(__file__).resolve().parents[4]
SIGNER = ServiceCredentialSigner(secret="synthetic-knowledge-service-identity-32-bytes")
PATH = "/api/v1/family/knowledge/questions"


def wire():
    payload = json.loads(
        (ROOT / "contracts/examples/valid/retrieval-response-v3.json").read_text(encoding="utf-8")
    )
    payload["data"]["request_id"] = "knowledge-test"
    payload["meta"] = {
        "correlation_id": "correlation-test",
        "timestamp": "2026-10-05T00:00:00Z",
        "schema_version": "1.0",
    }
    return payload


@pytest.fixture
def boundary(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    register_exception_handlers(app)
    client = SimpleNamespace(
        retrieve_public_knowledge=AsyncMock(
            return_value=FamilyKnowledgeAnswer(status="NO_DATA", answer="沒有足夠資料。")
        )
    )
    app.dependency_overrides[get_agent_runtime_client] = lambda: client
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id=uuid4(), actor_role="FAMILY_MEMBER", tenant_id=uuid4(), status="ACTIVE"
    )
    settings = SimpleNamespace(app_env="development", knowledge_router_v2_enabled=True)
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    return app, client, settings


@pytest.mark.asyncio
async def test_family_question_uses_server_scope_and_no_elder_context(boundary):
    app, upstream, _ = boundary
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PATH, json={"question": " 長照法第二條 ", "language": "zh-TW"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = upstream.retrieve_public_knowledge.call_args.kwargs["request_payload"]
    assert payload["audience"] == "family_caregiver"
    assert payload["purpose"] == "legal_reference"
    assert payload["query"] == "長照法第二條"
    assert set(payload) == {
        "schema_version",
        "request_id",
        "query",
        "query_profile",
        "top_k",
        "audience",
        "purpose",
        "language",
    }
    assert set(response.json()["data"]) == {"status", "answer", "sources"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,status",
    [
        ("ELDER", "ACTIVE"),
        ("HOME_CARE_WORKER", "ACTIVE"),
        ("ADMIN", "ACTIVE"),
        ("FAMILY_MEMBER", "SUSPENDED"),
    ],
)
async def test_other_roles_and_inactive_family_cannot_call_provider(boundary, role, status):
    app, upstream, _ = boundary
    app.dependency_overrides[get_actor_context] = lambda: ActorContext(
        actor_id=uuid4(), actor_role=role, tenant_id=uuid4(), status=status
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PATH, json={"question": "申請長照"})
    assert response.status_code == (403 if status != "ACTIVE" else 404)
    upstream.retrieve_public_knowledge.assert_not_called()


@pytest.mark.asyncio
async def test_anonymous_is_denied(boundary):
    app, upstream, _ = boundary

    async def anonymous():
        raise AuthenticationError("Authentication required")

    app.dependency_overrides[get_actor_context] = anonymous
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PATH, json={"question": "申請長照"})
    assert response.status_code == 401
    upstream.retrieve_public_knowledge.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra", ["audience", "elder_id", "tenant_id", "actor_role", "purpose", "session_id"]
)
async def test_scope_injection_rejected_without_echoing_input(boundary, extra):
    app, upstream, _ = boundary
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            PATH, json={"question": "申請長照", extra: "private-input-do-not-echo"}
        )
    assert response.status_code == 422
    assert "private-input-do-not-echo" not in response.text
    upstream.retrieve_public_knowledge.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["", "  ", "問" * 2001])
async def test_invalid_question_does_not_invoke_generation(boundary, question):
    app, upstream, _ = boundary
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PATH, json={"question": question})
    assert response.status_code == 422
    upstream.retrieve_public_knowledge.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("production", [False, True])
async def test_disabled_or_production_fails_closed(boundary, production):
    app, upstream, settings = boundary
    if production:
        settings.app_env = "production"
    else:
        settings.knowledge_router_v2_enabled = False
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PATH, json={"question": "申請長照"})
    assert response.status_code == 503
    upstream.retrieve_public_knowledge.assert_not_called()


@pytest.mark.asyncio
async def test_personal_record_request_never_leaves_core(boundary):
    app, upstream, _ = boundary
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(PATH, json={"question": "我媽媽昨天的照護紀錄呢？"})
    assert response.json()["data"]["status"] == "NO_DATA"
    upstream.retrieve_public_knowledge.assert_not_called()


def test_public_projection_contains_only_answer_and_official_source_metadata():
    payload = wire()
    payload["data"]["results"][0]["internal_note"] = "private-source-metadata"
    answer = public_answer(
        payload, request_id="knowledge-test", correlation_id="correlation-test", language="zh-TW"
    )
    assert answer.status == "ANSWER"
    assert "引用來源：" not in answer.answer
    assert "private-source-metadata" not in answer.model_dump_json()
    assert set(answer.sources[0].model_dump()) == {"title", "url", "locator", "current_status"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        None,
        "request",
        "correlation",
        "url",
        "credentials",
        "duplicate",
        "partial",
        "fallback",
        "malformed",
        "oversize",
        "http",
        "timeout",
    ],
)
async def test_signed_adapter_fails_closed_on_malformed_or_unbound_evidence(failure):
    payload = wire()
    if failure == "request":
        payload["data"]["request_id"] = "another-request"
    if failure == "correlation":
        payload["meta"]["correlation_id"] = "another-correlation"
    if failure == "url":
        payload["data"]["results"][0]["official_source_page_url"] = "https://example.com"
    if failure == "credentials":
        payload["data"]["results"][0]["official_source_page_url"] = (
            "https://private@www.mohw.gov.tw/"
        )
    if failure == "duplicate":
        payload["data"]["results"].append(copy.deepcopy(payload["data"]["results"][0]))
    if failure == "partial":
        payload["data"]["decision"] = "PARTIAL"
    if failure == "fallback":
        payload["data"]["status"] = "NO_DATA"

    async def handler(request):
        assert request.url.path == "/api/v3/rag/retrievals"
        assert request.headers.get(SERVICE_CREDENTIAL_HEADER)
        encoded = request.headers[SERVICE_CREDENTIAL_HEADER].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        assert claims["body_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert claims["path"] == request.url.path
        assert request.headers["X-Correlation-ID"] == "correlation-test"
        if failure == "timeout":
            raise httpx.ReadTimeout("private-provider-secret")
        if failure == "http":
            return httpx.Response(500, text="private-provider-secret")
        if failure == "malformed":
            return httpx.Response(200, text="private-provider-secret")
        if failure == "oversize":
            return httpx.Response(200, content=b"x" * 1_048_577)
        return httpx.Response(200, json=payload)

    client = AgentRuntimeClient(
        base_url="http://localhost:8001",
        timeout_seconds=1,
        credential_signer=SIGNER,
        transport=httpx.MockTransport(handler),
    )
    answer = await client.retrieve_public_knowledge(
        request_payload={"request_id": "knowledge-test", "language": "zh-TW"},
        correlation_id="correlation-test",
    )
    assert answer.status == ("ANSWER" if failure is None else "UNAVAILABLE")
    assert "private-provider-secret" not in answer.model_dump_json()


@pytest.mark.parametrize(
    "decision,reason,expected",
    [
        ("INSUFFICIENT", [], "NO_DATA"),
        ("CLARIFY", [], "CLARIFY"),
        ("INSUFFICIENT", ["SAFETY_GATE"], "BLOCKED"),
        ("FAILED", [], "UNAVAILABLE"),
    ],
)
def test_fallbacks_use_fixed_messages_and_never_forward_provider_text(decision, reason, expected):
    payload = wire()
    payload["data"].update(
        status="FAILED" if decision == "FAILED" else "NO_DATA",
        decision=decision,
        reason_codes=reason,
        results=[],
        answer_text=None,
        fallback_message="private-provider-secret",
    )
    answer = public_answer(
        payload, request_id="knowledge-test", correlation_id="correlation-test", language="en-US"
    )
    assert answer.status == expected
    assert answer.sources == []
    assert "private-provider-secret" not in answer.answer


def test_partial_answer_preserves_gap_and_strips_only_the_generated_citation_footer():
    payload = wire()
    payload["data"].update(
        decision="PARTIAL",
        missing_facets=["application step"],
        answer_text=(
            "Synthetic answer; application step is not covered." "\n\n引用來源：\nSynthetic footer"
        ),
    )
    answer = public_answer(
        payload, request_id="knowledge-test", correlation_id="correlation-test", language="en-US"
    )
    assert answer.status == "PARTIAL"
    assert answer.answer == "Synthetic answer; application step is not covered."
    assert answer.sources


@pytest.mark.asyncio
async def test_external_cancellation_propagates():
    async def handler(request):
        raise asyncio.CancelledError

    client = AgentRuntimeClient(
        base_url="http://localhost:8001",
        timeout_seconds=1,
        credential_signer=SIGNER,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(asyncio.CancelledError):
        await client.retrieve_public_knowledge(
            request_payload={"request_id": "knowledge-test", "language": "zh-TW"},
            correlation_id="correlation-test",
        )


@pytest.mark.asyncio
async def test_total_deadline_bounds_a_stream_that_never_finishes():
    closed = False

    class SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"{"
            await asyncio.sleep(60)

        async def aclose(self):
            nonlocal closed
            closed = True

    client = AgentRuntimeClient(
        base_url="http://localhost:8001",
        timeout_seconds=0.05,
        credential_signer=SIGNER,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowBody())),
    )
    answer = await asyncio.wait_for(
        client.retrieve_public_knowledge(
            request_payload={"request_id": "knowledge-test", "language": "en-US"},
            correlation_id="correlation-test",
        ),
        timeout=2,
    )
    assert answer.status == "UNAVAILABLE"
    assert closed
