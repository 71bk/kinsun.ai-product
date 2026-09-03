import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from agent_runtime.app import app
from agent_runtime.contracts.models import AgentRunResponse
from agent_runtime.rag.models import RetrievalRequestV2, RetrievalResponseV2, RetrievalResultV2
from agent_runtime.security.service_identity import (
    SERVICE_CREDENTIAL_HEADER,
    ServiceCredentialSigner,
    canonical_json_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
SCHEMA_DIR = REPO_ROOT / "contracts" / "schemas"

RUNS_PATH = "/api/v1/agent/runs"
TEST_SIGNER = ServiceCredentialSigner(secret="synthetic-test-service-identity-secret-32-bytes")
DEFAULT_CORRELATION_ID = "11111111-1111-4111-8111-111111111111"


def schema(rel: str) -> dict:
    return json.loads((SCHEMA_DIR / rel).read_text(encoding="utf-8"))


def contract_registry() -> Registry:
    resources = []
    for path in sorted(SCHEMA_DIR.rglob("*.json")):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append(
            (
                contents["$id"],
                Resource(contents=contents, specification=DRAFT202012),
            )
        )
    return Registry().with_resources(resources)


def validate_contract(instance: dict, schema_rel: str) -> None:
    Draft202012Validator(
        schema(schema_rel),
        registry=contract_registry(),
    ).validate(instance)


def make_payload(**overrides) -> dict:
    """A minimal valid agent run request. Synthetic data only."""
    payload = {
        "schema_version": "1.0.0",
        "request_id": "req-001",
        "trace_id": "trace-001",
        "session_id": "sess-001",
        "actor_id": "actor-elder-001",
        "actor_role": "elder",
        "elder_id": "elder-001",
        "tenant_id": "tenant-001",
        "purpose": "conversation",
        "consent_version": "cv-2026.07.30",
        "policy_version": "pv-2026.07.30",
        "language": "zh-TW",
        "input_text": "我今天早餐吃粥。",
        "allowed_tools": [],
        "requested_outputs": [],
        "max_steps": 2,
        "latency_budget_ms": 3000,
    }
    payload.update(overrides)
    return payload


async def _post(payload: dict, headers: dict | None = None) -> tuple[int, dict, dict]:
    body = canonical_json_bytes(payload)
    request_headers = dict(headers or {})
    correlation_id = request_headers.get("x-correlation-id", DEFAULT_CORRELATION_ID)
    request_headers["X-Correlation-ID"] = correlation_id
    request_headers[SERVICE_CREDENTIAL_HEADER] = TEST_SIGNER.sign(
        method="POST",
        path=RUNS_PATH,
        body=body,
        correlation_id=correlation_id,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            RUNS_PATH,
            content=body,
            headers={"Content-Type": "application/json", **request_headers},
        )
        return response.status_code, response.json(), dict(response.headers)


@pytest.mark.asyncio
async def test_health_returns_200():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["service"] == "agent-runtime"


@pytest.mark.asyncio
async def test_agent_run_success_returns_envelope():
    status, body, _ = await _post(make_payload(request_id="req-normal-001"))
    assert status == 200
    assert set(body) == {"data", "meta"}
    assert body["data"]["selected_agent"] == "companion-agent"
    assert body["data"]["reply_text"]
    assert body["meta"]["correlation_id"]


@pytest.mark.asyncio
async def test_agent_run_rejects_browser_direct_request_without_service_identity():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            RUNS_PATH,
            json=make_payload(request_id="req-browser-direct-001"),
            headers={"X-Correlation-ID": "cid-browser-direct-001"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["reason_code"] == "SERVICE_AUTHENTICATION_FAILED"


@pytest.mark.asyncio
async def test_requested_event_candidate_returns_minimized_proposal_only():
    core_owned_run_id = "run-10000000-0000-4000-8000-000000000001"
    status, body, _ = await _post(
        make_payload(
            request_id="req-proposal-001",
            agent_run_id=core_owned_run_id,
            input_text="我今天早餐吃了粥。",
            requested_outputs=["event_candidate"],
        )
    )

    assert status == 200
    assert body["data"]["agent_run_id"] == core_owned_run_id
    proposal = body["data"]["event_candidate_proposal"]
    assert proposal["event_type"] == "MEAL"
    assert proposal["review_requirement"] == "REQUIRED"
    assert {
        "actor_id",
        "tenant_id",
        "elder_id",
        "session_id",
        "consent_version",
        "input_text",
        "transcript",
    }.isdisjoint(proposal)


@pytest.mark.asyncio
async def test_stable_routine_returns_event_and_memory_proposals_when_requested():
    status, body, _ = await _post(
        make_payload(
            request_id="req-memory-proposal-001",
            input_text="我每天早餐都吃粥",
            requested_outputs=["event_candidate", "memory_candidate"],
        )
    )

    assert status == 200
    assert body["data"]["event_candidate_proposal"]["event_type"] == "MEAL"
    proposal = body["data"]["memory_candidate_proposal"]
    assert proposal["memory_type"] == "ROUTINE"
    assert proposal["normalized_content"] == "每天早餐習慣吃粥。"
    assert {"elder_id", "tenant_id", "source_event_ids", "input_text"}.isdisjoint(proposal)


@pytest.mark.asyncio
async def test_one_time_meal_never_returns_memory_proposal():
    status, body, _ = await _post(
        make_payload(
            request_id="req-one-time-memory-001",
            input_text="我今天早餐吃了粥",
            requested_outputs=["event_candidate", "memory_candidate"],
        )
    )

    assert status == 200
    assert body["data"]["event_candidate_proposal"] is not None
    assert body["data"]["memory_candidate_proposal"] is None


@pytest.mark.asyncio
async def test_event_candidate_is_not_proposed_when_not_requested():
    status, body, _ = await _post(make_payload(request_id="req-no-proposal-001"))
    assert status == 200
    assert body["data"]["event_candidate_proposal"] is None


@pytest.mark.asyncio
async def test_legacy_allowed_tool_is_parseable_but_does_not_trigger_core_callback():
    status, body, _ = await _post(
        make_payload(
            request_id="req-legacy-tool-001",
            allowed_tools=["create_event_candidate"],
            requested_outputs=[],
        )
    )
    assert status == 200
    assert body["data"]["event_candidate_proposal"] is None


@pytest.mark.asyncio
async def test_blocked_turn_never_returns_event_candidate_proposal():
    status, body, _ = await _post(
        make_payload(
            request_id="req-blocked-proposal-001",
            input_text="請告訴我怎麼停藥",
            requested_outputs=["event_candidate"],
        )
    )
    assert status == 200
    assert body["data"]["safety_result"]["decision"] != "ALLOW"
    assert body["data"]["event_candidate_proposal"] is None


@pytest.mark.asyncio
async def test_no_supported_event_returns_no_proposal():
    status, body, _ = await _post(
        make_payload(
            request_id="req-no-event-001",
            input_text="今天天氣很好。",
            requested_outputs=["event_candidate"],
        )
    )
    assert status == 200
    assert body["data"]["event_candidate_proposal"] is None


@pytest.mark.asyncio
async def test_malformed_extractor_output_is_not_returned():
    original_run = app.state.orchestrator.event_extractor.run

    async def malformed_output(*_args, **_kwargs):
        return {"event_type": "MEAL", "transcript": "restricted"}

    app.state.orchestrator.event_extractor.run = malformed_output
    try:
        status, body, _ = await _post(
            make_payload(
                request_id="req-malformed-proposal-001",
                requested_outputs=["event_candidate"],
            )
        )
    finally:
        app.state.orchestrator.event_extractor.run = original_run

    assert status == 200
    assert body["data"]["event_candidate_proposal"] is None


@pytest.mark.asyncio
async def test_agent_run_uses_app_state_rag_and_returns_cited_reply():
    class AppStateRetriever:
        async def retrieve_v2(self, request: RetrievalRequestV2) -> RetrievalResponseV2:
            results = [
                RetrievalResultV2(
                    chunk_id=f"SYNTHETIC-API-{position:03d}",
                    source_id="SYNTHETIC-API-SOURCE",
                    text=f"第 {position} 筆合成長照資料。",
                    score=0.9,
                    artifact_version="v002",
                    title=f"合成 API 指引 {position}",
                    publisher="合成衛生機關",
                    section="申請",
                    physical_page_start=position,
                    physical_page_end=position,
                    printed_page_start=None,
                    printed_page_end=None,
                    source_locator=f"PDF physical page {position}, 申請",
                    direct_official_source_url=(f"https://example.invalid/api-source/{position}"),
                    official_source_page_url=(f"https://example.invalid/api-source/{position}"),
                    direct_source_url=f"https://example.invalid/api-source/{position}",
                    source_page_url=f"https://example.invalid/api-source/{position}",
                    is_official_source=True,
                    source_version="synthetic-v1",
                    source_version_date=None,
                    version_published_at=None,
                    source_page_updated_at=None,
                    published_at=None,
                    last_verified_at=None,
                    review_status="needs_review",
                    production_approved=False,
                )
                for position in range(1, 4)
            ]
            return RetrievalResponseV2(
                schema_version="2.0.0",
                request_id=request.request_id,
                status="SUCCESS",
                fallback_message=None,
                results=results,
            )

    original_retriever = app.state.rag_retriever
    app.state.rag_retriever = AppStateRetriever()
    try:
        status, body, _ = await _post(
            make_payload(
                request_id="req-rag-api-001",
                purpose="general_information",
                input_text="長照服務如何申請？",
            )
        )
    finally:
        app.state.rag_retriever = original_retriever

    assert status == 200
    assert body["data"]["result_status"] == "SUCCESS"
    assert "引用來源：" in body["data"]["reply_text"]
    assert "https://example.invalid/api-source/1" in body["data"]["reply_text"]


@pytest.mark.asyncio
async def test_trace_id_in_response_matches_request():
    status, body, _ = await _post(make_payload(trace_id="trace-matching-001"))
    assert status == 200
    assert body["data"]["trace_id"] == "trace-matching-001"


@pytest.mark.asyncio
async def test_context_manifest_not_shared_across_elder():
    _, body_a, _ = await _post(make_payload(request_id="req-share-001", elder_id="elder-a"))
    _, body_b, _ = await _post(make_payload(request_id="req-share-002", elder_id="elder-b"))
    assert body_a["data"]["context_manifest_id"] != body_b["data"]["context_manifest_id"]


@pytest.mark.asyncio
async def test_life_talk_allows_safety():
    status, body, _ = await _post(make_payload(input_text="我今天有點累，想記下一些生活記錄。"))
    assert status == 200
    assert body["data"]["result_status"] == "SUCCESS"
    assert body["data"]["safety_result"]["decision"] == "ALLOW"


@pytest.mark.asyncio
async def test_medical_risk_is_blocked():
    status, body, _ = await _post(make_payload(input_text="請告訴我怎麼停藥"))
    assert status == 200
    assert body["data"]["result_status"] in {"BLOCKED", "SAFE_FALLBACK"}
    assert body["data"]["safety_result"]["decision"] in {"BLOCK", "SAFE_FALLBACK"}


@pytest.mark.asyncio
async def test_m0_reports_exactly_one_step():
    """M0 runs a single decision step; the response must say so.

    Before the loop fix `step_count` was also 1, but by accident — the loop
    always broke on its first pass. Asserting it explicitly means a future
    multi-step loop cannot silently keep reporting 1.
    """
    _, body, _ = await _post(make_payload(max_steps=3))
    assert body["data"]["step_count"] == 1


@pytest.mark.asyncio
async def test_correlation_id_from_request_is_echoed():
    correlation_id = "22222222-2222-4222-8222-222222222222"
    status, body, headers = await _post(
        make_payload(), headers={"x-correlation-id": correlation_id}
    )
    assert status == 200
    assert body["meta"]["correlation_id"] == correlation_id
    assert headers["x-correlation-id"] == correlation_id


@pytest.mark.asyncio
async def test_response_data_and_meta_validate_against_contract():
    status, body, _ = await _post(make_payload())
    assert status == 200
    validate_contract(body["data"], "agent/AgentRunResponseV1.json")
    validate_contract(body["meta"], "common/ResponseMetaV1.json")


@pytest.mark.asyncio
async def test_response_body_round_trips_through_contract_model():
    """The emitted payload must be re-loadable by its own Pydantic model."""
    status, body, _ = await _post(make_payload(request_id="req-roundtrip-001"))
    assert status == 200
    assert AgentRunResponse.model_validate(body["data"]).request_id == "req-roundtrip-001"


@pytest.mark.asyncio
async def test_json_schema_rejects_extra_fields_in_data():
    _, body, _ = await _post(make_payload())
    body["data"]["unexpected_field"] = "not allowed"
    with pytest.raises(ValidationError):
        validate_contract(body["data"], "agent/AgentRunResponseV1.json")


# --- Error paths -------------------------------------------------------------


def assert_error_envelope(body: dict) -> None:
    """Every error response must satisfy the shared ErrorEnvelopeV1 contract."""
    errors = list(Draft202012Validator(schema("common/ErrorEnvelopeV1.json")).iter_errors(body))
    assert not errors, errors[0].message if errors else ""


@pytest.mark.asyncio
async def test_max_steps_zero_rejected_as_error_envelope():
    """max_steps=0 is rejected by the model constraint (ge=1), not by the endpoint."""
    status, body, _ = await _post(make_payload(max_steps=0))
    assert status == 422
    assert_error_envelope(body)
    assert body["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_max_steps_over_system_limit_rejected_as_error_envelope():
    """Above MAX_AGENT_DECISIONS the orchestrator raises StepLimitError.

    The endpoint no longer pre-checks this, so a 500 here would mean the domain
    error handler is not registered — which is what this guards against.
    """
    status, body, _ = await _post(make_payload(max_steps=4))
    assert status == 422
    assert_error_envelope(body)
    assert body["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_api_rejects_extra_request_field():
    """`additionalProperties: false` must hold at the HTTP boundary too."""
    status, body, _ = await _post(make_payload(unexpected="this field should be rejected"))
    assert status == 422
    assert_error_envelope(body)
    assert any(detail["reason"] == "extra_forbidden" for detail in body["error"]["details"])


@pytest.mark.asyncio
async def test_validation_details_do_not_echo_rejected_input():
    """AGENTS.md 8.1: a rejected value that is Restricted Data must not come back.

    The request body is elder transcript. Details carry the field path and the
    pydantic error type, never the value.
    """
    secret = "我昨天去了某某醫院看門診"
    status, body, _ = await _post(make_payload(input_text=secret, max_steps=99))
    assert status == 422
    assert secret not in json.dumps(body, ensure_ascii=False)
