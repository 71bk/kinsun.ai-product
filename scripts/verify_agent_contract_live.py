"""Validate real Agent Runtime responses against the published contract.

Runs the app in-process and checks that what it actually returns conforms to
contracts/. A contract that has never been checked against the running service
is just prose.

The Core API counterpart (verify_contract_live.py) needs a database; this one
needs nothing — the mock provider is local and deterministic, so this check is
cheap enough to run on every change.

    cd services/agent-runtime
    uv run --with pyyaml --with jsonschema --with referencing \
        python ../../scripts/verify_agent_contract_live.py ../../contracts
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

# agent-runtime uses a src/ layout and is installed as `package = false`, so the
# package is not importable from the service directory the way core-api's `app`
# is. Resolve it from this script's own location rather than relying on the
# caller's PYTHONPATH, so the documented command works as written.
SERVICE_SRC = Path(__file__).resolve().parents[1] / "services" / "agent-runtime" / "src"
sys.path.insert(0, str(SERVICE_SRC))

# Keep this verifier deterministic and ensure it never reads repository or
# service-local .env files. Core calls are exercised through MockTransport.
os.environ["APP_ENV"] = "test"
os.environ["MODEL_PROVIDER"] = "mock"
os.environ["RAG_MODE"] = "disabled"
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["SERVICE_IDENTITY_ENABLED"] = "true"
os.environ["SERVICE_IDENTITY_HMAC_SECRET"] = (
    "synthetic-live-contract-service-identity-secret-32-bytes"
)

from agent_runtime.app import create_app  # noqa: E402
from agent_runtime.rag.client import OpenSearchClient  # noqa: E402
from agent_runtime.rag.hybrid_search import HybridSearch  # noqa: E402
from agent_runtime.rag.models import (  # noqa: E402
    HybridProfileSettings,
    HybridSearchSettings,
)
from agent_runtime.rag.retriever import Retriever  # noqa: E402
from agent_runtime.security.service_identity import (  # noqa: E402
    SERVICE_CREDENTIAL_HEADER,
    ServiceCredentialSigner,
)

CONTRACTS = Path(sys.argv[1])
OPENAPIS = {
    1: yaml.safe_load(
        (CONTRACTS / "openapi" / "agent-runtime.v1.yaml").read_text(encoding="utf-8")
    ),
    2: yaml.safe_load(
        (CONTRACTS / "openapi" / "agent-runtime.v2.yaml").read_text(encoding="utf-8")
    ),
}

RUNS_PATH = "/api/v1/agent/runs"
RAG_PATH = "/api/v1/rag/retrievals"
RAG_V2_PATH = "/api/v2/rag/retrievals"

failures: list[str] = []


class LiveContractServiceAuth(httpx.Auth):
    """Sign each in-process private request without persisting its body or credential."""

    def __init__(self) -> None:
        self._signer = ServiceCredentialSigner(
            secret="synthetic-live-contract-service-identity-secret-32-bytes"
        )

    def auth_flow(self, request: httpx.Request):  # noqa: ANN201
        correlation_id = request.headers.get("X-Correlation-ID") or (
            f"live-contract-{uuid.uuid4()}"
        )
        request.headers["X-Correlation-ID"] = correlation_id
        request.headers[SERVICE_CREDENTIAL_HEADER] = self._signer.sign(
            method=request.method,
            path=request.url.path,
            body=request.content,
            correlation_id=correlation_id,
        )
        yield request


FORBIDDEN_PROPOSAL_FIELDS = frozenset(
    {
        "actor_id",
        "actor_role",
        "agent_run_id",
        "authorization",
        "consent_version",
        "elder_id",
        "full_prompt",
        "input_text",
        "policy_version",
        "prompt",
        "purpose",
        "request_id",
        "session_id",
        "source_id",
        "source_event_ids",
        "source_type",
        "source_version",
        "tenant_id",
        "trace_id",
        "transcript",
        "transcript_text",
    }
)


def registry() -> Registry:
    reg = Registry()
    for path in sorted((CONTRACTS / "schemas").rglob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(
            schema["$id"],
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
    return reg


REG = registry()


def load(rel: str) -> dict:
    return json.loads((CONTRACTS / "schemas" / rel).read_text(encoding="utf-8"))


def _component_id(name: str, openapi: dict) -> str:
    """Absolute $id of the schema file that components/schemas/<name> points at."""
    rel = openapi["components"]["schemas"][name]["$ref"]
    target = (CONTRACTS / "openapi" / rel).resolve()
    return json.loads(target.read_text(encoding="utf-8"))["$id"]


def _resolve_component_refs(node, openapi: dict):
    """Rewrite `#/components/schemas/X` to X's absolute `$id`.

    An inline OpenAPI response schema is not a standalone JSON Schema: its
    document-relative pointers only resolve inside the OpenAPI file. Rewriting
    them to the `$id` the registry already knows lets the envelope shape
    itself — `required: [data, meta]`, `additionalProperties: false` — be
    checked, instead of only checking `data` and `meta` in isolation.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            return {
                **node,
                "$ref": _component_id(ref.rsplit("/", 1)[1], openapi),
            }
        return {key: _resolve_component_refs(value, openapi) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_component_refs(item, openapi) for item in node]
    return node


def inline_schema(path: str, method: str, status: str) -> dict:
    """Pull the inline response schema the OpenAPI doc declares for a path."""
    openapi = OPENAPIS[2 if path.startswith("/api/v2/") else 1]
    node = openapi["paths"][path][method]["responses"][status]
    return _resolve_component_refs(
        node["content"]["application/json"]["schema"],
        openapi,
    )


def check(label: str, payload: dict, schema: dict) -> None:
    errors = list(Draft202012Validator(schema, registry=REG).iter_errors(payload))
    if errors:
        failures.append(f"{label}: {errors[0].message}")
        print(f"FAIL  {label}: {errors[0].message}")
    else:
        print(f"ok    {label}")


def expect_status(label: str, actual: int, wanted: int) -> bool:
    if actual != wanted:
        failures.append(f"{label}: got {actual}, expected {wanted}")
        print(f"FAIL  {label}: got {actual}, expected {wanted}")
        return False
    print(f"ok    {label}")
    return True


def find_forbidden_proposal_fields(value: object, path: str = "$") -> list[str]:
    """Return recursive field paths that would leak Core-owned or restricted data."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_PROPOSAL_FIELDS:
                found.append(child_path)
            found.extend(find_forbidden_proposal_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_forbidden_proposal_fields(child, f"{path}[{index}]"))
    return found


def make_payload(**overrides) -> dict:
    """Synthetic request. Never use real elder data here."""
    payload = {
        "schema_version": "1.0.0",
        "request_id": "req-live-001",
        "trace_id": "trace-live-001",
        "session_id": "sess-live-001",
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


def make_rag_payload(**overrides) -> dict:
    """Synthetic staging retrieval request with no elder or tenant data."""
    payload = {
        "schema_version": "1.0.0",
        "request_id": "req-rag-live-001",
        "query": "居家服務的申請條件是什麼？",
        "query_profile": "natural_language",
        "top_k": 5,
        "language": "zh-TW",
    }
    payload.update(overrides)
    return payload


def make_rag_v2_payload(**overrides) -> dict:
    payload = make_rag_payload(
        schema_version="2.0.0",
        request_id="req-rag-v2-live-001",
        audience="elder",
        purpose="general_information",
    )
    payload.update(overrides)
    return payload


class LiveQueryEmbedder:
    dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * self.dimension


class LiveSearchTransport:
    def __init__(self, *, incomplete: bool) -> None:
        self._incomplete = incomplete

    def search(self, **kwargs: object) -> dict[str, object]:
        return {
            "hits": {
                "hits": [
                    _live_v2_hit(
                        number,
                        missing_locator=self._incomplete and number == 3,
                    )
                    for number in range(1, 6)
                ]
            }
        }


def _live_v2_hit(number: int, *, missing_locator: bool) -> dict[str, object]:
    source_url = f"https://example.invalid/live-governed/{number}"
    return {
        "_id": f"live-governed-{number}",
        "_score": 1.0 - number / 20,
        "_source": {
            "chunk_id": f"live-governed-{number}",
            "source_id": "live-governed-source",
            "text": f"Synthetic governed live evidence {number}",
            "artifact_version": "v002",
            "title": "Synthetic Governed Live Guide",
            "publisher": None,
            "section": "Synthetic section",
            "physical_page_start": None,
            "physical_page_end": None,
            "printed_page_start": None,
            "printed_page_end": None,
            "source_locator": None if missing_locator else f"Web section {number}",
            "direct_official_source_url": source_url,
            "official_source_page_url": source_url,
            "direct_source_url": source_url,
            "source_page_url": source_url,
            "is_official_source": True,
            "source_version": None,
            "source_version_date": None,
            "version_published_at": None,
            "source_page_updated_at": None,
            "published_at": None,
            "last_verified_at": None,
            "review_status": "needs_review",
            "production_approved": False,
            "storage_url": "https://storage.example.invalid/private-object",
            "current_status": "current",
            "stop_normal_rag": False,
            "risk_level": "low",
            "requires_official_assessment": False,
            "requires_professional_assessment": False,
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["general_information"],
            "retrieval_eligible": True,
            "retrieval_block_reasons": [],
        },
    }


def build_live_v2_retriever(*, incomplete: bool) -> Retriever:
    natural = HybridProfileSettings(
        profile="natural_language",
        search_pipeline="live-natural",
        bm25_weight=0.4,
        vector_weight=0.6,
        vector_min_score=0.7,
        top_k=5,
        agent_chunk_min=3,
        agent_chunk_max=5,
    )
    legal = HybridProfileSettings(
        profile="legal",
        search_pipeline="live-legal",
        bm25_weight=0.65,
        vector_weight=0.35,
        vector_min_score=0.7,
        top_k=5,
        agent_chunk_min=3,
        agent_chunk_max=5,
    )
    hybrid_settings = HybridSearchSettings(
        index_alias="rag-live-staging",
        natural_language=natural,
        legal=legal,
    )
    return Retriever(
        embedding_provider=LiveQueryEmbedder(),
        search_backend=OpenSearchClient(
            LiveSearchTransport(incomplete=incomplete),
            hybrid_settings,
        ),
        hybrid_search=HybridSearch(hybrid_settings),
        allow_needs_review_citations=True,
    )


async def main() -> int:
    app = create_app()
    # Make this contract check deterministic and network-free even when the
    # caller's shell happens to contain AWS/OpenSearch environment variables.
    # The executable boundary must be safe when no retrieval adapter exists.
    app.state.rag_retriever = None
    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
            auth=LiveContractServiceAuth(),
        ) as client,
    ):
        response = await client.get("/health")
        check(
            "GET /health 200 vs contract",
            response.json(),
            inline_schema("/health", "get", "200"),
        )

        # Staging RAG remains callable without AWS/OpenSearch. It must return a
        # schema-valid, explicit fail-closed outcome with no partial chunks and
        # must never copy the query into the fallback response.
        private_query = "合成查詢-不得回填-9f6c2b1a"
        response = await client.post(
            RAG_PATH,
            json=make_rag_payload(query=private_query),
        )
        if expect_status(
            f"POST {RAG_PATH} unconfigured returns 200", response.status_code, 200
        ):
            body = response.json()
            check(
                f"POST {RAG_PATH} unconfigured body vs contract",
                body,
                inline_schema(RAG_PATH, "post", "200"),
            )
            rag_data = body.get("data", {})
            if rag_data.get("status") != "FAILED":
                failures.append(
                    f"unconfigured RAG reported status={rag_data.get('status')}, expected FAILED"
                )
                print(f"FAIL  unconfigured RAG status: {rag_data.get('status')}")
            else:
                print("ok    unconfigured RAG reports FAILED")
            if rag_data.get("results") != []:
                failures.append("unconfigured RAG returned partial results")
                print("FAIL  unconfigured RAG returned partial results")
            else:
                print("ok    unconfigured RAG returns no partial results")
            fallback = rag_data.get("fallback_message")
            if not isinstance(fallback, str) or not fallback.strip():
                failures.append(
                    "unconfigured RAG omitted its explicit fallback message"
                )
                print("FAIL  unconfigured RAG omitted its explicit fallback message")
            else:
                print("ok    unconfigured RAG provides an explicit fallback")
            serialized = json.dumps(body, ensure_ascii=False)
            if private_query in serialized:
                failures.append("unconfigured RAG response echoed the rejected query")
                print("FAIL  unconfigured RAG response echoed the query")
            else:
                print("ok    unconfigured RAG response does not echo the query")

        # Request-schema failure must use ErrorEnvelope and keep the rejected
        # query out of field-level validation details.
        rejected_query = "合成錯誤查詢-不得回填-5a8d7e3c"
        response = await client.post(
            RAG_PATH,
            json=make_rag_payload(
                query=rejected_query,
                top_k=10,
                caller_dsl={"match_all": {}},
            ),
        )
        if expect_status(
            f"POST {RAG_PATH} invalid body returns 422", response.status_code, 422
        ):
            body = response.json()
            check(
                f"POST {RAG_PATH} 422 body vs ErrorEnvelopeV1",
                body,
                load("common/ErrorEnvelopeV1.json"),
            )
            if rejected_query in json.dumps(body, ensure_ascii=False):
                failures.append("RAG validation response echoed the rejected query")
                print("FAIL  RAG validation response echoed the rejected query")
            else:
                print("ok    RAG validation response does not echo the rejected query")

        v2_private_query = "synthetic-v2-private-query-7d39a2"
        response = await client.post(
            RAG_V2_PATH,
            json=make_rag_v2_payload(query=v2_private_query),
        )
        if expect_status(
            f"POST {RAG_V2_PATH} unconfigured returns 200",
            response.status_code,
            200,
        ):
            body = response.json()
            check(
                f"POST {RAG_V2_PATH} unconfigured body vs contract",
                body,
                inline_schema(RAG_V2_PATH, "post", "200"),
            )
            if body.get("data", {}).get("status") != "FAILED":
                failures.append("unconfigured V2 RAG did not report FAILED")
                print("FAIL  unconfigured V2 RAG did not report FAILED")
            else:
                print("ok    unconfigured V2 RAG reports FAILED")
            if v2_private_query in json.dumps(body, ensure_ascii=False):
                failures.append("unconfigured V2 RAG echoed the rejected query")
                print("FAIL  unconfigured V2 RAG echoed the rejected query")
            else:
                print("ok    unconfigured V2 RAG does not echo the query")

        app.state.rag_retriever = build_live_v2_retriever(incomplete=False)
        response = await client.post(RAG_V2_PATH, json=make_rag_v2_payload())
        if expect_status(
            f"POST {RAG_V2_PATH} governed success returns 200",
            response.status_code,
            200,
        ):
            body = response.json()
            check(
                f"POST {RAG_V2_PATH} governed success body vs contract",
                body,
                inline_schema(RAG_V2_PATH, "post", "200"),
            )
            results = body.get("data", {}).get("results", [])
            if len(results) != 5 or any(not result.get("source_locator") for result in results):
                failures.append("V2 RAG omitted complete source locators")
                print("FAIL  V2 RAG omitted complete source locators")
            else:
                print("ok    V2 RAG returns five complete source locators")
            serialized = json.dumps(body, ensure_ascii=False)
            if "storage_url" in serialized or "storage.example.invalid" in serialized:
                failures.append("V2 RAG exposed an internal storage URL")
                print("FAIL  V2 RAG exposed an internal storage URL")
            else:
                print("ok    V2 RAG excludes internal storage URLs")

        app.state.rag_retriever = build_live_v2_retriever(incomplete=True)
        response = await client.post(RAG_V2_PATH, json=make_rag_v2_payload())
        if expect_status(
            f"POST {RAG_V2_PATH} incomplete citation returns 200",
            response.status_code,
            200,
        ):
            body = response.json()
            check(
                f"POST {RAG_V2_PATH} incomplete citation body vs contract",
                body,
                inline_schema(RAG_V2_PATH, "post", "200"),
            )
            data = body.get("data", {})
            if data.get("status") != "NO_DATA" or data.get("results") != []:
                failures.append("V2 RAG exposed a partial incomplete citation batch")
                print("FAIL  V2 RAG exposed a partial incomplete citation batch")
            else:
                print("ok    V2 RAG fails the incomplete citation batch closed")

        app.state.rag_retriever = None

        # Normal turn.
        response = await client.post(RUNS_PATH, json=make_payload())
        if expect_status(f"POST {RUNS_PATH} returns 200", response.status_code, 200):
            check(
                f"POST {RUNS_PATH} 200 body vs contract",
                response.json(),
                inline_schema(RUNS_PATH, "post", "200"),
            )

        # Safety-blocked turn is still a 200 with the same envelope — the
        # contract must not describe refusal as a transport error.
        response = await client.post(
            RUNS_PATH, json=make_payload(input_text="請告訴我怎麼停藥")
        )
        if expect_status(
            f"POST {RUNS_PATH} blocked turn returns 200", response.status_code, 200
        ):
            body = response.json()
            check(
                f"POST {RUNS_PATH} blocked body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body["data"]["result_status"] not in {"BLOCKED", "SAFE_FALLBACK"}:
                failures.append(
                    f"blocked turn reported result_status={body['data']['result_status']}"
                )
                print(
                    f"FAIL  blocked turn result_status: {body['data']['result_status']}"
                )
            else:
                print("ok    blocked turn reports a non-success result_status")

        # Schema rejection.
        response = await client.post(RUNS_PATH, json=make_payload(unexpected="nope"))
        if expect_status(
            f"POST {RUNS_PATH} extra field returns 422", response.status_code, 422
        ):
            check(
                "422 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

        # Over the system step ceiling: must reach the domain error handler,
        # not the catch-all. A 500 here means the handler is unregistered.
        response = await client.post(RUNS_PATH, json=make_payload(max_steps=99))
        if expect_status(
            f"POST {RUNS_PATH} above step ceiling returns 422",
            response.status_code,
            422,
        ):
            check(
                "step-limit 422 body vs ErrorEnvelopeV1",
                response.json(),
                load("common/ErrorEnvelopeV1.json"),
            )

        # The rejected body is elder transcript and must not come back.
        secret = "我昨天去了某某醫院看門診"
        response = await client.post(
            RUNS_PATH, json=make_payload(input_text=secret, max_steps=99)
        )
        if secret in response.text:
            failures.append("error response echoed the rejected input_text")
            print("FAIL  error response echoed the rejected input_text")
        else:
            print("ok    error response does not echo rejected input")

        # Runtime returns a minimized proposal only when Core explicitly asks
        # for one. Runtime never registers an AgentRun or invokes a Core Tool.
        core_owned_run_id = "run-a0000000-0000-4000-8000-000000000011"
        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-proposal-live-001",
                trace_id="trace-proposal-live-001",
                agent_run_id=core_owned_run_id,
                input_text="我今天早餐吃了粥。",
                requested_outputs=["event_candidate"],
            ),
        )
        if expect_status("proposal-only run returns 200", response.status_code, 200):
            body = response.json()
            check(
                "proposal-only response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            data = body.get("data", {})
            if data.get("agent_run_id") != core_owned_run_id:
                failures.append(
                    "proposal-only response changed the Core-owned AgentRun ID"
                )
                print("FAIL  proposal-only response changed the Core-owned AgentRun ID")
            else:
                print(
                    "ok    proposal-only response preserves the Core-owned AgentRun ID"
                )

            proposal = data.get("event_candidate_proposal")
            if not isinstance(proposal, dict):
                failures.append("requested meal proposal was null or not an object")
                print("FAIL  requested meal proposal was null or not an object")
            else:
                check(
                    "event candidate proposal vs contract",
                    proposal,
                    load("agent/EventCandidateProposalV1.json"),
                )
                forbidden_paths = find_forbidden_proposal_fields(proposal)
                if forbidden_paths:
                    failures.append(
                        "event candidate proposal leaked restricted/Core-owned fields: "
                        + ", ".join(forbidden_paths)
                    )
                    print(
                        "FAIL  event candidate proposal leaked restricted/Core-owned fields: "
                        + ", ".join(forbidden_paths)
                    )
                else:
                    print(
                        "ok    event candidate proposal recursively omits "
                        "identity/session/consent/policy/transcript/input fields"
                    )

        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-memory-proposal-live-001",
                trace_id="trace-memory-proposal-live-001",
                input_text="我每天早餐都吃粥",
                requested_outputs=["event_candidate", "memory_candidate"],
            ),
        )
        if expect_status("memory proposal run returns 200", response.status_code, 200):
            body = response.json()
            check(
                "memory proposal response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            data = body.get("data", {})
            if not isinstance(data.get("event_candidate_proposal"), dict):
                failures.append(
                    "memory proposal run did not also return its source event proposal"
                )
                print(
                    "FAIL  memory proposal run did not also return its source event proposal"
                )
            else:
                print("ok    memory proposal run also returns a source event proposal")

            memory_proposal = data.get("memory_candidate_proposal")
            if not isinstance(memory_proposal, dict):
                failures.append(
                    "requested stable-routine memory proposal was null or not an object"
                )
                print(
                    "FAIL  requested stable-routine memory proposal was null or not an object"
                )
            else:
                check(
                    "memory candidate proposal vs contract",
                    memory_proposal,
                    load("agent/MemoryCandidateProposalV1.json"),
                )
                forbidden_paths = find_forbidden_proposal_fields(memory_proposal)
                if forbidden_paths:
                    failures.append(
                        "memory candidate proposal leaked restricted/Core-owned fields: "
                        + ", ".join(forbidden_paths)
                    )
                    print(
                        "FAIL  memory candidate proposal leaked restricted/Core-owned fields: "
                        + ", ".join(forbidden_paths)
                    )
                else:
                    print(
                        "ok    memory candidate proposal recursively omits "
                        "identity/session/consent/source/transcript/input fields"
                    )

        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-one-time-memory-live-001",
                input_text="我今天早餐吃了粥",
                requested_outputs=["event_candidate", "memory_candidate"],
            ),
        )
        if expect_status(
            "one-time meal memory request returns 200", response.status_code, 200
        ):
            data = response.json().get("data", {})
            if data.get("event_candidate_proposal") is None:
                failures.append("one-time meal did not return its event proposal")
                print("FAIL  one-time meal did not return its event proposal")
            elif data.get("memory_candidate_proposal") is not None:
                failures.append("one-time meal incorrectly returned a memory proposal")
                print("FAIL  one-time meal incorrectly returned a memory proposal")
            else:
                print(
                    "ok    one-time meal returns an event proposal but no memory proposal"
                )

        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-blocked-proposal-live-001",
                input_text="請告訴我怎麼停藥",
                requested_outputs=["event_candidate", "memory_candidate"],
            ),
        )
        if expect_status(
            "blocked proposal request returns 200", response.status_code, 200
        ):
            body = response.json()
            check(
                "blocked proposal response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("event_candidate_proposal") is not None:
                failures.append("blocked turn returned an event candidate proposal")
                print("FAIL  blocked turn returned an event candidate proposal")
            else:
                print("ok    blocked turn returns a null event candidate proposal")
            if body.get("data", {}).get("memory_candidate_proposal") is not None:
                failures.append("blocked turn returned a memory candidate proposal")
                print("FAIL  blocked turn returned a memory candidate proposal")
            else:
                print("ok    blocked turn returns a null memory candidate proposal")

        response = await client.post(
            RUNS_PATH,
            json=make_payload(
                request_id="req-no-event-proposal-live-001",
                input_text="今天天氣很好。",
                requested_outputs=["event_candidate"],
            ),
        )
        if expect_status(
            "no-event proposal request returns 200", response.status_code, 200
        ):
            body = response.json()
            check(
                "no-event proposal response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("event_candidate_proposal") is not None:
                failures.append("no-event turn returned an event candidate proposal")
                print("FAIL  no-event turn returned an event candidate proposal")
            else:
                print("ok    no-event turn returns a null event candidate proposal")

        # Patch only after the in-process client exists. A legacy Tool name
        # remains parseable, but it must not make Runtime create an outbound
        # HTTP client or turn the compatibility field into a proposal request.
        from unittest.mock import patch

        legacy_response: httpx.Response | None = None
        with patch.object(
            httpx,
            "AsyncClient",
            side_effect=AssertionError(
                "Runtime attempted to create an external HTTP client"
            ),
        ) as external_client_constructor:
            try:
                legacy_response = await client.post(
                    RUNS_PATH,
                    json=make_payload(
                        request_id="req-legacy-tool-live-001",
                        allowed_tools=["create_event_candidate"],
                        requested_outputs=[],
                    ),
                )
            except AssertionError:
                # The constructor call itself is asserted below so the verifier
                # can report the contract failure instead of aborting early.
                pass

        if external_client_constructor.call_count:
            failures.append(
                "legacy allowed_tools path instantiated an external HTTP client"
            )
            print(
                "FAIL  legacy allowed_tools path instantiated an external HTTP client"
            )
        else:
            print("ok    legacy allowed_tools path creates no external HTTP client")

        if legacy_response is None:
            if not external_client_constructor.call_count:
                failures.append(
                    "legacy allowed_tools request did not return a response"
                )
                print("FAIL  legacy allowed_tools request did not return a response")
        elif expect_status(
            "legacy allowed_tools request returns 200",
            legacy_response.status_code,
            200,
        ):
            body = legacy_response.json()
            check(
                "legacy allowed_tools response body vs contract",
                body,
                inline_schema(RUNS_PATH, "post", "200"),
            )
            if body.get("data", {}).get("event_candidate_proposal") is not None:
                failures.append(
                    "legacy allowed_tools alone produced an event candidate proposal"
                )
                print(
                    "FAIL  legacy allowed_tools alone produced an event candidate proposal"
                )
            else:
                print("ok    legacy allowed_tools alone produces no proposal")

    return len(failures)


if __name__ == "__main__":
    code = asyncio.run(main())
    print(
        "\nall live contract checks passed"
        if code == 0
        else f"\n{code} live contract failure(s)"
    )
    raise SystemExit(code)
