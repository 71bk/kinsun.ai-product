from __future__ import annotations

from hashlib import sha256

import pytest

from agent_runtime.rag.evidence_models import RetrievalRequestV3
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import HybridProfileSettings, HybridSearchSettings
from agent_runtime.rag.retriever import Retriever
from agent_runtime.rag.search_backend import SearchHit

RELEASE = "knowledge-v007-synthetic"
PROFILE = "ep-google-synthetic"


class Embedding:
    dimension = 3

    async def embed_query(self, query):
        self.query = query
        return [0.1, 0.2, 0.3]


class Backend:
    def __init__(self, hits):
        self.hits = hits

    async def search(self, plan):
        self.plan = plan
        return self.hits


def hit(identifier="official-1", **changes):
    text = f"Synthetic official public guidance {identifier}."
    source = {
        "chunk_id": identifier,
        "source_id": "official-source",
        "text": text,
        "text_sha256": sha256(text.encode()).hexdigest(),
        "release_id": RELEASE,
        "embedding_profile_id": PROFILE,
        "artifact_version": "v007",
        "title": "Synthetic official guide",
        "publisher": None,
        "section": None,
        "source_locator": "Official web section",
        "physical_page_start": None,
        "physical_page_end": None,
        "printed_page_start": None,
        "printed_page_end": None,
        "direct_official_source_url": "https://example.gov.tw/guide",
        "official_source_page_url": None,
        "direct_source_url": "https://example.gov.tw/guide",
        "source_page_url": None,
        "is_official_source": True,
        "source_version": None,
        "source_version_date": None,
        "version_published_at": None,
        "source_page_updated_at": None,
        "published_at": None,
        "last_verified_at": None,
        "review_status": "needs_review",
        "production_approved": False,
        "data_classification": "public",
        "distribution_scope": "public_knowledge",
        "current_status": "current",
        "risk_level": "low",
        "stop_normal_rag": False,
        "retrieval_eligible": True,
        "retrieval_block_reasons": [],
        "allowed_audiences": ["elder"],
        "allowed_purposes": ["general_information", "legal_reference"],
        "requires_official_assessment": False,
        "requires_professional_assessment": False,
        **changes,
    }
    return SearchHit(score=0.9, source=source)


def setup(hits):
    def profile(name):
        return HybridProfileSettings(
            profile=name,
            search_pipeline=f"synthetic-{name}",
            bm25_weight=0.4,
            vector_weight=0.6,
            vector_min_score=0.7,
            top_k=5,
            agent_chunk_min=3,
            agent_chunk_max=5,
        )

    backend, embedding = Backend(hits), Embedding()
    retriever = Retriever(
        embedding_provider=embedding,
        search_backend=backend,
        hybrid_search=HybridSearch(
            HybridSearchSettings(
                index_alias="synthetic",
                natural_language=profile("natural_language"),
                legal=profile("legal"),
            )
        ),
        public_release_id=RELEASE,
        public_embedding_profile_id=PROFILE,
    )
    return retriever, backend, embedding


def request(*, legal=False):
    return RetrievalRequestV3(
        schema_version="3.0.0",
        request_id="synthetic-request",
        query="A previously unlisted natural question about local public services?",
        query_profile="legal" if legal else "natural_language",
        top_k=5,
        audience="elder",
        purpose="legal_reference" if legal else "general_information",
        language="zh-TW",
    )


@pytest.mark.asyncio
async def test_unlisted_natural_question_can_return_one_source_without_legacy_pool():
    retriever, backend, embedding = setup([hit()])
    req = request()
    results = await retriever.load_public_candidates(req, require_current=False)
    assert len(results) == 1
    assert embedding.query == req.query
    assert backend.plan.public_knowledge_mode is True
    assert backend.plan.require_current is False
    assert backend.plan.search_result_limit == 50
    assert backend.plan.policy_candidate_chunk_ids is None
    assert backend.plan.allow_needs_review is False
    assert results[0].review_status == "needs_review"
    assert results[0].section == "Official web section"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"release_id": "wrong-release"},
        {"text_sha256": "0" * 64},
        {"embedding_profile_id": "wrong-profile"},
    ],
)
async def test_release_and_text_hash_drift_reject_entire_candidate_batch(changes):
    retriever, _, _ = setup([hit("valid"), hit("drift", **changes)])
    with pytest.raises(ValueError, match="content binding"):
        await retriever.load_public_candidates(request(), require_current=False)


@pytest.mark.asyncio
async def test_duplicate_chunk_ids_keep_first_hit_and_stable_order():
    retriever, _, _ = setup([hit("a"), hit("a", title="Duplicate title"), hit("b")])
    results = await retriever.load_public_candidates(request(), require_current=False)
    assert [r.chunk_id for r in results] == ["a", "b"]
    assert results[0].title == "Synthetic official guide"


@pytest.mark.asyncio
async def test_retired_false_eligibility_and_unknown_assessment_bind_advisory():
    retriever, _, _ = setup(
        [
            hit(
                retrieval_eligible=False,
                retrieval_block_reasons=["human_source_review_pending"],
                requires_official_assessment=None,
                requires_professional_assessment=None,
            )
        ]
    )
    results = await retriever.load_public_candidates(request(), require_current=False)
    assert len(results) == 1
    assert results[0].assessment_advisory_required is True
    assert results[0].requires_official_assessment is True
    assert results[0].requires_professional_assessment is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"allowed_audiences": []},
        {"allowed_purposes": ["professional_reference"]},
        {"stop_normal_rag": True},
        {"current_status": "superseded"},
        {"data_classification": "restricted"},
    ],
)
async def test_explicit_restrictions_are_rejected(changes):
    retriever, _, _ = setup([hit(**changes)])
    assert await retriever.load_public_candidates(request(), require_current=False) == []


@pytest.mark.asyncio
async def test_unknown_currency_warning_and_current_requirement_reach_search_plan():
    retriever, backend, _ = setup([hit(current_status="unknown")])
    results = await retriever.load_public_candidates(request(), require_current=False)
    assert "source_currency_unknown" in results[0].warnings
    assert await retriever.load_public_candidates(request(), require_current=True) == []
    assert backend.plan.require_current is True
    assert await retriever.load_public_candidates(request(legal=True), require_current=False) == []
