from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import (
    HybridProfileSettings,
    HybridSearchSettings,
    RetrievalRequestV2,
)
from agent_runtime.rag.retriever import Retriever
from agent_runtime.rag.runtime_policy import (
    RuntimePolicyError,
    load_source_family_runtime_policy,
)
from agent_runtime.rag.search_backend import SearchHit

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
POLICY_PATH = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v002/"
    "source-family-runtime-policy.json"
)
V1_POLICY_PATH = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/runtime/candidates/v001/"
    "source-family-runtime-policy.json"
)
GOLDEN_PATH = REPOSITORY_ROOT / "config/rag/source-family-golden-queries-v002.json"
CHUNK_ROOT = REPOSITORY_ROOT / "data/rag-v3/candidates/v003/chunks"


class FakeEmbeddingProvider:
    dimension = 3

    async def embed_query(self, query: str) -> list[float]:
        assert query
        return [0.1, 0.2, 0.3]

    async def aclose(self) -> None:
        return None


class GoldenBackend:
    def __init__(self, hits: list[SearchHit]) -> None:
        self.hits = hits
        self.plans = []

    async def search(self, plan):
        self.plans.append(plan)
        return self.hits

    async def aclose(self) -> None:
        return None


def _load_policy():
    digest = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
    return load_source_family_runtime_policy(POLICY_PATH, expected_sha256=digest)


def _text_by_successor_chunk_id() -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(CHUNK_ROOT.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            result[row["identity"]["chunk_id"]] = row["content"]["text"]
    return result


def _hybrid_search() -> HybridSearch:
    return HybridSearch(
        HybridSearchSettings(
            index_alias="kinsun-staging",
            natural_language=HybridProfileSettings(
                profile="natural_language",
                search_pipeline="natural-staging",
                bm25_weight=0.4,
                vector_weight=0.6,
                vector_min_score=0.1,
                top_k=5,
                agent_chunk_min=3,
                agent_chunk_max=5,
            ),
            legal=HybridProfileSettings(
                profile="legal",
                search_pipeline="legal-staging",
                bm25_weight=0.7,
                vector_weight=0.3,
                vector_min_score=0.1,
                top_k=5,
                agent_chunk_min=3,
                agent_chunk_max=5,
            ),
        )
    )


def test_runtime_policy_is_hash_pinned_and_has_fixed_candidate_scope() -> None:
    policy = _load_policy()

    assert len(policy.candidate_chunk_ids) == 554
    assert len(set(policy.candidate_chunk_ids)) == 554
    assert policy.document.summary.source_count == 14
    assert policy.document.runtime_policy_version == "v002"
    assert policy.document.summary.response_metadata_ready_count == 522
    assert policy.document.global_policy.retrieval_audiences == (
        "elder",
        "family_caregiver",
        "care_professional",
        "system_admin",
    )
    assert policy.document.gates.production_approved is False


def test_runtime_v001_remains_loadable_without_mutating_prior_semantics() -> None:
    digest = hashlib.sha256(V1_POLICY_PATH.read_bytes()).hexdigest()
    policy = load_source_family_runtime_policy(V1_POLICY_PATH, expected_sha256=digest)

    assert policy.document.runtime_policy_version == "v001"
    assert policy.document.summary.response_metadata_ready_count == 302


def test_runtime_policy_rejects_bad_digest_and_production_forgery(tmp_path: Path) -> None:
    raw = POLICY_PATH.read_bytes()
    with pytest.raises(RuntimePolicyError, match="SHA-256 mismatch"):
        load_source_family_runtime_policy(POLICY_PATH, expected_sha256="0" * 64)

    document = json.loads(raw)
    document["gates"]["production_approved"] = True
    forged = tmp_path / "forged.json"
    forged.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    digest = hashlib.sha256(forged.read_bytes()).hexdigest()
    with pytest.raises(RuntimePolicyError, match="contract is invalid"):
        load_source_family_runtime_policy(forged, expected_sha256=digest)


@pytest.mark.asyncio
async def test_offline_golden_queries_retrieve_before_response_policy() -> None:
    policy = _load_policy()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    text_by_chunk = _text_by_successor_chunk_id()
    by_prior = {candidate.prior_chunk_id: candidate for candidate in policy.document.chunks}

    assert golden["scope"] == "OFFLINE_POLICY_ADVISORY_AND_CITATION_GATE_ONLY"
    assert golden["live_relevance_evaluation"] == "NOT_EXECUTED"
    assert len(golden["cases"]) == 9
    for case in golden["cases"]:
        hits = []
        for number, prior_chunk_id in enumerate(case["fixture_prior_chunk_ids"]):
            candidate = by_prior[prior_chunk_id]
            hits.append(
                SearchHit(
                    score=0.99 - number / 100,
                    source={
                        "chunk_id": prior_chunk_id,
                        "source_id": candidate.source_id,
                        "text": text_by_chunk[candidate.chunk_id],
                    },
                )
            )
        backend = GoldenBackend(hits)
        retriever = Retriever(
            embedding_provider=FakeEmbeddingProvider(),
            search_backend=backend,
            hybrid_search=_hybrid_search(),
            allow_needs_review_citations=True,
            source_family_policy=policy,
        )
        response = await retriever.retrieve_v2(
            RetrievalRequestV2(
                schema_version="2.0.0",
                request_id=f"golden-{case['case_id']}",
                query=case["query"],
                query_profile=(
                    "legal" if case["purpose"] == "legal_reference" else "natural_language"
                ),
                top_k=5,
                audience=case["audience"],
                purpose=case["purpose"],
                language="zh-TW",
            )
        )

        assert backend.plans, f"{case['case_id']} did not reach the search backend"
        plan = backend.plans[0]
        assert plan.search_result_limit == 50
        assert len(plan.policy_candidate_chunk_ids or ()) == 554
        assert response.status == case["expected_status"], case["case_id"]
        if response.status == "SUCCESS":
            assert len(response.results) == 3
            assert all(result.artifact_version == "v003" for result in response.results)
            assert all(result.review_status == "verified" for result in response.results)
            assert not any(result.production_approved for result in response.results)
            assert (
                any(result.assessment_advisory_required for result in response.results)
                is case["expected_advisory"]
            )
        else:
            assert response.results == []
            assert case["expected_advisory"] is False


def test_high_risk_and_research_exclusions_are_absent_from_search_projection() -> None:
    policy = _load_policy()
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    successor_ids = {candidate.chunk_id for candidate in policy.document.chunks}
    source_ids = {candidate.source_id for candidate in policy.document.chunks}

    high_risk, research = golden["exclusion_cases"]
    assert high_risk["successor_chunk_id"] not in successor_ids
    assert research["source_id"] not in source_ids
    assert high_risk["expected_projection_presence"] is False
    assert research["expected_projection_presence"] is False
