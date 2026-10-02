"""Synthetic support sets only; no human approval is asserted by these tests."""

from datetime import UTC, datetime
from hashlib import sha256
from types import SimpleNamespace

import pytest

from agent_runtime.contracts.models import AgentRunRequest
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.orchestrator import AgentOrchestrator
from agent_runtime.rag.evidence_models import RetrievalResponseV3, RetrievalResultV3
from agent_runtime.rag.evidence_retrieval import EvidenceRetriever
from agent_runtime.rag.evidence_sufficiency import (
    EvidenceCandidate,
    EvidencePolicy,
    EvidenceRequest,
    EvidenceSufficiencyEvaluator,
    ReviewedClaim,
    ReviewedScope,
    SupportMember,
    SupportSet,
    render,
)
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import HybridProfileSettings, HybridSearchSettings, RetrievalResultV2
from agent_runtime.rag.retriever import Retriever
from agent_runtime.rag.search_backend import SearchHit

POLICY_HASH = "a" * 64
RUNTIME_HASH = "b" * 64


def make_result(number, *, official_assessment=False):
    result = RetrievalResultV2(
        chunk_id=f"citation-{number}",
        source_id="synthetic-source",
        text=f"Synthetic complete condition {number}",
        score=0.9,
        artifact_version="v003",
        title=f"Synthetic Guide {number}",
        publisher="Synthetic Publisher",
        section="Application",
        physical_page_start=number,
        physical_page_end=number,
        printed_page_start=None,
        printed_page_end=None,
        source_locator=f"Page {number}",
        direct_official_source_url=f"https://example.test/guide/{number}",
        official_source_page_url=None,
        direct_source_url=f"https://example.test/guide/{number}",
        source_page_url=None,
        is_official_source=True,
        source_version="synthetic-v1",
        source_version_date=None,
        version_published_at=None,
        source_page_updated_at=None,
        published_at=None,
        last_verified_at=None,
        review_status="verified",
        production_approved=False,
    )
    result.bind_assessment_requirements(official=official_assessment, professional=False)
    return result


def request(**changes):
    return EvidenceRequest(
        request_id="synthetic-evidence-request",
        query="synthetic application question",
        role="elder",
        purpose="general_information",
        release_id="synthetic-release",
        policy_sha256=POLICY_HASH,
        runtime_policy_sha256=RUNTIME_HASH,
        scope_id="synthetic-scope",
    ).model_copy(update=changes)


def candidate(number=1):
    result = make_result(number, official_assessment=True)
    result.review_status = "verified"
    return EvidenceCandidate(
        request_id=request().request_id,
        search_chunk_id=f"search-{number}",
        release_id=request().release_id,
        runtime_policy_sha256=RUNTIME_HASH,
        result=result,
        live_source={
            "chunk_id": f"search-{number}",
            "source_id": result.source_id,
            "text": result.text,
            "current_status": "current",
            "stop_normal_rag": False,
            "retrieval_eligible": True,
            "retrieval_block_reasons": [],
            "risk_level": "low",
            "review_status": "verified",
            "production_approved": False,
            "requires_official_assessment": True,
            "requires_professional_assessment": False,
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["general_information"],
        },
    )


def policy(count=1):
    members = tuple(
        SupportMember(
            search_chunk_id=c.search_chunk_id,
            citation_chunk_id=c.result.chunk_id,
            source_id=c.result.source_id,
            text_sha256=sha256(c.result.text.encode()).hexdigest(),
        )
        for c in (candidate(n) for n in range(1, count + 1))
    )
    scope = ReviewedScope(
        scope_id="synthetic-scope",
        queries=(request().query,),
        roles=("elder",),
        purposes=("general_information",),
        topic="application",
        required_facets=("conditions",),
        claims=(
            ReviewedClaim(
                claim_id="claim-1",
                text="合成申請資訊。",
                qualifiers=("須符合全部合成條件。",),
                facets=("conditions",),
            ),
        ),
        support_sets=(
            SupportSet(
                set_id="support-1", members=members, claim_ids=("claim-1",), facets=("conditions",)
            ),
        ),
        valid_from=datetime(2020, 1, 1, tzinfo=UTC),
        valid_until=datetime(2099, 1, 1, tzinfo=UTC),
        review_status="REVIEWED",
    )
    return EvidencePolicy(
        policy_id="synthetic-policy",
        release_id=request().release_id,
        runtime_policy_sha256=RUNTIME_HASH,
        review_status="REVIEWED",
        usage="SYNTHETIC_TEST_ONLY",
        scopes=(scope,),
    )


def evaluator(count=1):
    return EvidenceSufficiencyEvaluator(policy(count), POLICY_HASH, synthetic_mode=True)


@pytest.mark.parametrize("count", [1, 2])
def test_complete_atomic_support_set_renders_all_qualifiers_and_citations(count):
    decision = evaluator(count).evaluate(request(), [candidate(n) for n in range(1, count + 1)])
    assert decision.status == "SUFFICIENT"
    answer = render(decision)
    assert "須符合全部合成條件。" in answer
    assert "主管機關" in answer
    for n in range(1, count + 1):
        assert candidate(n).result.source_url in answer


def test_five_hits_missing_required_condition_are_not_answerable():
    decision = evaluator(2).evaluate(request(), [candidate(n) for n in (1, 3, 4, 5, 6)])
    assert decision.status == "INSUFFICIENT"
    assert decision.selected_candidates == decision.claims == ()
    assert "合成申請資訊" not in render(decision)


def test_support_set_above_five_cannot_be_truncated():
    assert (
        evaluator(6).evaluate(request(), [candidate(n) for n in range(1, 6)]).status
        == "INSUFFICIENT"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"policy_sha256": "c" * 64},
        {"runtime_policy_sha256": "c" * 64},
        {"release_id": "drift"},
        {"query": "other question"},
        {"role": "system_admin"},
        {"purpose": "legal_reference"},
        {"scope_id": None},
    ],
)
def test_request_policy_scope_binding_drift_is_unknown(change):
    assert evaluator().evaluate(request(**change), [candidate()]).status == "UNKNOWN"


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_status", "expired"),
        ("stop_normal_rag", True),
        ("retrieval_eligible", False),
        ("retrieval_block_reasons", ["blocked"]),
        ("risk_level", "unknown"),
        ("review_status", "needs_review"),
        ("allowed_audiences", ["system_admin"]),
        ("allowed_purposes", ["legal_reference"]),
        ("requires_official_assessment", None),
        ("text", "changed source text"),
        ("source_id", "other source"),
    ],
)
def test_live_gate_or_hash_drift_denies_without_partial_evidence(field, value):
    c = candidate()
    c = c.model_copy(update={"live_source": {**c.live_source, field: value}})
    decision = evaluator().evaluate(request(), [c])
    assert decision.status == "INSUFFICIENT"
    assert not decision.selected_candidates


@pytest.mark.parametrize(
    "change",
    [{"request_id": "other-request"}, {"release_id": "drift"}, {"runtime_policy_sha256": "c" * 64}],
)
def test_candidate_binding_drift_denies(change):
    assert (
        evaluator().evaluate(request(), [candidate().model_copy(update=change)]).status
        == "INSUFFICIENT"
    )


def test_expired_pending_or_synthetic_policy_is_unknown_without_override():
    p = policy()
    assert (
        EvidenceSufficiencyEvaluator(p, POLICY_HASH).evaluate(request(), [candidate()]).status
        == "UNKNOWN"
    )
    pending = p.model_copy(update={"review_status": "PENDING"})
    assert (
        EvidenceSufficiencyEvaluator(pending, POLICY_HASH, synthetic_mode=True)
        .evaluate(request(), [candidate()])
        .status
        == "UNKNOWN"
    )
    expired = evaluator().evaluate(request(), [candidate()], now=datetime(2100, 1, 1, tzinfo=UTC))
    assert expired.status == "UNKNOWN"


def test_missing_clarification_and_facets_do_not_generate():
    p = policy()
    scope = p.scopes[0].model_copy(update={"clarification_facets": ("service_code",)})
    e = EvidenceSufficiencyEvaluator(
        p.model_copy(update={"scopes": (scope,)}), POLICY_HASH, synthetic_mode=True
    )
    assert e.evaluate(request(), [candidate()]).status == "CLARIFY"
    assert (
        e.evaluate(request(clarified_facets=("service_code",)), [candidate()]).status
        == "SUFFICIENT"
    )
    scope = p.scopes[0].model_copy(update={"required_facets": ("missing-condition",)})
    e = EvidenceSufficiencyEvaluator(
        p.model_copy(update={"scopes": (scope,)}), POLICY_HASH, synthetic_mode=True
    )
    assert e.evaluate(request(), [candidate()]).status == "INSUFFICIENT"


@pytest.mark.asyncio
async def test_opt_in_adapter_has_no_model_and_does_not_search_unknown_scopes():
    calls = []

    async def loader(req):
        calls.append(req)
        return [candidate()]

    adapter = EvidenceRetriever(loader, evaluator())
    assert (await adapter.retrieve_evidence(request())).status == "UNKNOWN"
    adapter.enabled = True
    assert (await adapter.retrieve_evidence(request(scope_id=None))).status == "UNKNOWN"
    assert calls == []
    assert (await adapter.retrieve_evidence(request())).status == "SUFFICIENT"


@pytest.mark.asyncio
async def test_adapter_failure_is_sanitized_and_empty():
    async def loader(req):
        raise RuntimeError("private query or provider detail")

    decision = await EvidenceRetriever(loader, evaluator(), enabled=True).retrieve_evidence(
        request()
    )
    assert decision.status == "FAILED"
    assert "private" not in render(decision)
    assert decision.selected_candidates == ()


def test_controlled_render_refuses_to_truncate_qualifiers():
    decision = evaluator().evaluate(request(), [candidate()])
    claim = decision.claims[0].model_copy(update={"qualifiers": ("長" * 4100,)})
    with pytest.raises(ValueError, match="truncation"):
        render(decision.model_copy(update={"claims": (claim,)}))


def test_duplicate_citation_ids_and_assessment_drift_are_rejected():
    first = candidate()
    second = candidate(2).model_copy(update={"result": first.result})
    assert evaluator(2).evaluate(request(), [first, second]).status == "UNKNOWN"
    first.result.bind_assessment_requirements(official=False, professional=False)
    assert evaluator().evaluate(request(), [first]).status == "INSUFFICIENT"


def test_missing_citation_revalidated_even_for_untrusted_model_copy():
    c = candidate()
    broken = c.result.model_copy(
        update={"direct_source_url": None, "direct_official_source_url": None}
    )
    assert (
        evaluator().evaluate(request(), [c.model_copy(update={"result": broken})]).status
        == "INSUFFICIENT"
    )


def agent_request(input_text="synthetic application question"):
    return AgentRunRequest.model_validate(
        {
            "schema_version": "1.0.0",
            "request_id": request().request_id,
            "session_id": "synthetic-session",
            "actor_id": "synthetic-elder",
            "actor_role": "elder",
            "elder_id": "synthetic-elder",
            "tenant_id": "synthetic-tenant",
            "purpose": "general_information",
            "consent_version": "synthetic-consent",
            "policy_version": "synthetic-policy",
            "language": "zh-TW",
            "input_text": input_text,
            "allowed_tools": [],
            "max_steps": 3,
            "latency_budget_ms": 3000,
        }
    )


class NeverGenerate(ModelProvider):
    async def generate_reply(self, request, context_manifest, language):
        raise AssertionError("V3 must never call the model")


class SyntheticService:
    def __init__(self, status="SUFFICIENT", answer=None, request_id=None):
        self.status, self.answer, self.request_id = status, answer, request_id
        self.calls = []

    async def retrieve_v3(self, req):
        self.calls.append(req)
        if self.status != "SUFFICIENT":
            return RetrievalResponseV3(
                request_id=req.request_id,
                status="NO_DATA",
                decision=self.status,
                fallback_message="合成資料不足。",
            )
        decision = evaluator().evaluate(request(), [candidate()])
        citation_data = candidate().result.model_dump()
        citation_data.update(
            direct_official_source_url="https://synthetic.mohw.gov.tw/guide",
            official_source_page_url=None,
            direct_source_url="https://synthetic.mohw.gov.tw/guide",
        )
        return RetrievalResponseV3(
            request_id=self.request_id or req.request_id,
            status="SUCCESS",
            decision="SUFFICIENT",
            results=[RetrievalResultV3(**citation_data, current_status="current")],
            answer_text=self.answer or render(decision),
            release_id=request().release_id,
            embedding_profile_id="synthetic-profile",
            policy_version="public-knowledge-v1",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["SUFFICIENT", "UNKNOWN", "INSUFFICIENT", "CLARIFY"])
async def test_orchestrator_v3_success_and_fallback_never_call_model(status):
    service = SyntheticService(status)
    response = await AgentOrchestrator(NeverGenerate(), max_steps=3).run(
        agent_request(), evidence_retriever=service
    )
    assert len(service.calls) == 1
    assert service.calls[0].query == agent_request().input_text
    if status == "SUFFICIENT":
        assert "須符合全部合成條件。" in response.reply_text
        assert response.safety_result.decision.value == "ALLOW"
    else:
        assert response.safety_result.decision.value == "SAFE_FALLBACK"
        assert "Synthetic Guide" not in response.reply_text


@pytest.mark.asyncio
async def test_orchestrator_v3_input_and_output_safety_gates_and_request_binding():
    orchestrator = AgentOrchestrator(NeverGenerate(), max_steps=3)
    service = SyntheticService()
    response = await orchestrator.run(agent_request("我要停藥"), evidence_retriever=service)
    assert service.calls == []
    assert response.safety_result.decision.value == "BLOCK"
    response = await orchestrator.run(
        agent_request(), evidence_retriever=SyntheticService(answer="可以服用藥物")
    )
    assert response.safety_result.decision.value == "BLOCK"
    response = await orchestrator.run(
        agent_request(), evidence_retriever=SyntheticService(request_id="other-request")
    )
    assert response.safety_result.decision.value == "SAFE_FALLBACK"


@pytest.mark.asyncio
async def test_output_safety_fallback_discards_evidence_context_and_raw_legal_query_stays_exact():
    class CapturingOrchestrator(AgentOrchestrator):
        def _response(self, **kwargs):
            self.final_manifest = kwargs["context_manifest"]
            return super()._response(**kwargs)

    orchestrator = CapturingOrchestrator(NeverGenerate(), max_steps=3)
    service = SyntheticService(answer="可以服用藥物")
    await orchestrator.run(agent_request("長照法的合成申請條件"), evidence_retriever=service)
    assert service.calls[0].query == "長照法的合成申請條件"
    assert service.calls[0].query_profile == "natural_language"
    assert all(item.source_type != "rag-approved" for item in orchestrator.final_manifest.items)


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", [False, True])
async def test_backend_adapter_preserves_search_citation_binding_and_defective_batch_denies(broken):
    c = candidate()
    citation_values = c.result.model_dump(exclude={"chunk_id", "source_id", "text", "score"})
    if broken:
        citation_values["source_locator"] = ""
    binding = SimpleNamespace(
        prior_chunk_id=c.search_chunk_id,
        chunk_id=c.result.chunk_id,
        source_id=c.result.source_id,
        citation=SimpleNamespace(**citation_values),
        effective_risk_level="low",
        retrieval_audiences=("elder",),
        source_allowed_purposes=("general_information",),
        chunk_allowed_purposes=("general_information",),
        requires_official_assessment=True,
        requires_professional_assessment=False,
    )

    class SyntheticRuntimePolicy:
        sha256 = RUNTIME_HASH
        document = SimpleNamespace(
            projection_binding=SimpleNamespace(release_id="synthetic-release")
        )
        candidate_chunk_ids = tuple(
            [c.search_chunk_id] + [f"synthetic-unused-{i}" for i in range(553)]
        )

        def response_candidate(self, source, *, audience, purpose):
            return binding

    class Embedder:
        dimension = 1

        async def embed_query(self, query):
            return [0.1]

    class Backend:
        async def search(self, plan):
            return [SearchHit(source=c.live_source, score=0.9)]

    profiles = {}
    for name in ("natural_language", "legal"):
        profiles[name] = HybridProfileSettings(
            profile=name,
            search_pipeline=f"synthetic-{name}",
            bm25_weight=0.4,
            vector_weight=0.6,
            vector_min_score=0.7,
            top_k=5,
            agent_chunk_min=3,
            agent_chunk_max=5,
        )
    retriever = Retriever(
        embedding_provider=Embedder(),
        search_backend=Backend(),
        hybrid_search=HybridSearch(
            HybridSearchSettings(index_alias="synthetic-staging", **profiles)
        ),
        source_family_policy=SyntheticRuntimePolicy(),
        allow_needs_review_citations=True,
    )
    if broken:
        with pytest.raises(ValueError, match="defective"):
            await retriever.load_evidence_candidates(request())
    else:
        candidates = await retriever.load_evidence_candidates(request())
        assert len(candidates) == 1
        assert candidates[0].search_chunk_id == "search-1"
        assert candidates[0].result.chunk_id == "citation-1"
        assert evaluator().evaluate(request(), candidates).status == "SUFFICIENT"
