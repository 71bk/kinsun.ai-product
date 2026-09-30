"""Opt-in, bounded synthetic evaluation using Google embeddings + read-only PostgreSQL.

Run with agent-runtime Python from the repository root. Default evaluates one
variant per semantic group (40), all purposes force-probed to isolate retrieval
from routing. --all-variants evaluates all 120. Never activates a release, writes
DB rows, invokes generation, or reports draft anchors as exhaustive relevance.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/agent-runtime/src"))

from evaluate_quality import evidence_anchors, load_cases, load_corpus, manifest  # noqa: E402
from quality_metrics import ranking_metrics  # noqa: E402
from quality_search import STRATEGIES, candidates, governed_results, rank  # noqa: E402

from agent_runtime.app import build_configured_rag_retriever  # noqa: E402
from agent_runtime.orchestration.rag_integration import _retrieval_query  # noqa: E402
from agent_runtime.rag.models import RetrievalRequestV2  # noqa: E402
from agent_runtime.rag.postgres_backend import PostgresSearchBackend  # noqa: E402
from agent_runtime.rag.query_normalization import normalize_legal_query  # noqa: E402


def summarize(rows):
    output = {}
    for name in sorted({r["experiment"] for r in rows}):
        subset = [r for r in rows if r["experiment"] == name]
        labeled = [r for r in subset if r["anchors"]["recall"] is not None]
        negative = [r for r in subset if r["category"] == "off_domain"]
        output[name] = {
            "case_count": len(subset),
            "anchor_case_count": len(labeled),
            "anchor_recall_at_5": statistics.mean(
                r["anchors"]["recall"] for r in labeled
            )
            if labeled
            else None,
            "anchor_ndcg_at_5": statistics.mean(r["anchors"]["ndcg"] for r in labeled)
            if labeled
            else None,
            "success_count": sum(r["status"] == "SUCCESS" for r in subset),
            "offdomain_no_data": {
                "passed": sum(r["status"] == "NO_DATA" for r in negative),
                "count": len(negative),
            },
            "insufficient_count": sum(r["status"] == "INSUFFICIENT" for r in subset),
        }
    return output


async def evaluate(args):
    document, all_cases = load_cases(args.dataset)
    cases = (
        all_cases
        if args.all_variants
        else [c for c in all_cases if c["case_id"].endswith("-1")]
    )
    if len(cases) > 120:
        raise ValueError("Maximum 120 synthetic cases")
    corpus = load_corpus()
    retriever = build_configured_rag_retriever()
    if retriever is None:
        raise ValueError("Configured staging retriever unavailable")
    rows, timing, cache = [], [], {}
    embedding_calls = 0
    try:
        backend = retriever._search_backend
        pinned = manifest(args.dataset)
        if (
            not isinstance(backend, PostgresSearchBackend)
            or backend._settings.release_id != pinned["storage_release"]
        ):
            raise ValueError("Evaluation requires pinned PostgreSQL release")
        if backend._settings.embedding_profile_id != pinned["embedding_profile"]:
            raise ValueError("Evaluation embedding profile mismatch")
        if retriever._source_family_policy is None or retriever._allow_all_audiences:
            raise ValueError(
                "Pinned policy required; all-audiences override prohibited"
            )
        policy = retriever._source_family_policy
        policy_file = (
            "data/rag-v3/governance/source-family-policy/runtime/candidates/v004/"
            "source-family-runtime-policy.json"
        )
        if policy.sha256 != pinned["input_sha256"][policy_file]:
            raise ValueError("Runtime policy differs from evaluation manifest")
        citation_to_storage = {
            c.chunk_id: storage_id
            for storage_id, c in policy._by_prior_chunk_id.items()
        }
        expected_embedding = ("google", "gemini-embedding-001", 1024)
        configured_embedding = backend._embedding_settings
        if (
            configured_embedding.provider,
            configured_embedding.model_id,
            configured_embedding.dimension,
        ) != expected_embedding:
            raise ValueError(
                "Query embedding configuration differs from pinned profile"
            )
        from agent_runtime.rag.models import HybridProfileSettings

        for profile_name, file_name in (
            ("natural_language", "hybrid-natural-language.json"),
            ("legal", "hybrid-legal.json"),
        ):
            expected_profile = HybridProfileSettings.from_config(
                json.loads(
                    (ROOT / "config/rag" / file_name).read_text(encoding="utf-8")
                )
            )
            if (
                retriever._hybrid_search._settings.for_profile(profile_name)
                != expected_profile
            ):
                raise ValueError("Search weights differ from pinned configuration")
        cache_path = ROOT / ".qa/rag-quality-embeddings-v1.json"
        cache_binding = pinned["input_sha256"]["config/rag/embedding-google.yaml"]
        if cache_path.exists():
            saved = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                saved.get("binding") == cache_binding
                and saved.get("profile") == pinned["embedding_profile"]
            ):
                cache = saved["vectors"]
        # Factory validates the configured policy digest and release/profile binding.
        for case in cases:
            profile = (
                "legal" if case["purpose"] == "legal_reference" else "natural_language"
            )
            original = _retrieval_query(profile, case["query"])
            variants = {
                "original": original,
                "normalized": normalize_legal_query(original)
                if profile == "legal"
                else original,
            }
            for spelling, query in variants.items():
                start = time.perf_counter()
                query_key = hashlib.sha256(query.encode("utf-8")).hexdigest()
                if query_key not in cache:
                    vector = await asyncio.wait_for(
                        retriever._embedding_provider.embed_query(query), timeout=35
                    )
                    cache[query_key] = vector
                    embedding_calls += 1
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(
                        json.dumps(
                            {
                                "binding": cache_binding,
                                "profile": pinned["embedding_profile"],
                                "vectors": cache,
                            }
                        ),
                        encoding="utf-8",
                    )
                vector = cache[query_key]
                if len(vector) != 1024 or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in vector
                ):
                    raise ValueError("Invalid cached embedding")
                request = RetrievalRequestV2(
                    schema_version="2.0.0",
                    request_id=str(uuid4()),
                    query=query,
                    query_profile=profile,
                    top_k=5,
                    audience="family_caregiver",
                    purpose="legal_reference"
                    if profile == "legal"
                    else "general_information",
                    language="zh-TW",
                )
                plan = retriever._hybrid_search.build_v2(
                    request,
                    vector,
                    allow_needs_review=retriever._allow_needs_review_citations,
                    policy_candidate_chunk_ids=retriever._source_family_policy.candidate_chunk_ids,
                )
                diagnostic = await candidates(backend, plan)
                elapsed = round((time.perf_counter() - start) * 1000, 2)
                timing.append(elapsed)
                # Compare replay to the real adapter for every original query.
                if spelling == "original":
                    actual = await backend.search(plan)
                    replay = rank(diagnostic, "hybrid", plan.min_score)
                    if [h.source["chunk_id"] for h in actual] != [
                        r["chunk_id"] for r in replay
                    ]:
                        raise ValueError("Baseline SQL replay differs from runtime")
                anchors = evidence_anchors(case, corpus)
                for strategy in STRATEGIES:
                    selected = rank(diagnostic, strategy, plan.min_score)
                    governed = governed_results(selected, request, retriever)
                    status = (
                        "INVALID_CITATION"
                        if governed is None
                        else "NO_DATA"
                        if not governed
                        else "INSUFFICIENT"
                        if len(governed) < 3
                        else "SUCCESS"
                    )
                    final = governed if status == "SUCCESS" else []
                    eligible_anchors = set(anchors).intersection(
                        r["chunk_id"] for r in diagnostic
                    )
                    if (
                        set(
                            citation_to_storage[r.chunk_id] for r in final
                        ).intersection(anchors)
                        - eligible_anchors
                    ):
                        raise ValueError(
                            "Citation/storage identity mapping is inconsistent"
                        )
                    rows.append(
                        {
                            "case_id": case["case_id"],
                            "split": case["split"],
                            "category": case["category"],
                            "experiment": f"{spelling}/{strategy}",
                            "status": status,
                            "candidate_count": len(diagnostic),
                            "post_floor_count": len(selected),
                            "governed_before_minimum": len(governed or []),
                            "candidate_anchor_recall": ranking_metrics(
                                [r["chunk_id"] for r in diagnostic], anchors, k=100
                            )["recall"],
                            "post_floor_anchor_recall": ranking_metrics(
                                [r["chunk_id"] for r in selected], anchors, k=50
                            )["recall"],
                            "pre_minimum_anchor_recall": ranking_metrics(
                                [
                                    citation_to_storage[r.chunk_id]
                                    for r in (governed or [])
                                ],
                                anchors,
                            )["recall"],
                            "anchors": ranking_metrics(
                                [citation_to_storage[r.chunk_id] for r in final],
                                anchors,
                            ),
                            "ranked_ids": [r.chunk_id for r in final],
                            "storage_ids": [
                                citation_to_storage[r.chunk_id] for r in final
                            ],
                            "citation_versions": sorted(
                                {r.artifact_version for r in final}
                            ),
                            "review_statuses": sorted({r.review_status for r in final}),
                        }
                    )
            print(
                json.dumps(
                    {
                        "completed_case": case["case_id"],
                        "embedding_calls": embedding_calls,
                    }
                ),
                flush=True,
            )
        return {
            "schema_version": "1.0",
            "mode": "LIVE_RETRIEVAL_DRAFT_ANCHORS",
            "created_at": datetime.now(UTC).isoformat(),
            "manifest": pinned,
            "case_count": len(cases),
            "audience": "family_caregiver",
            "qrel_scope": document["qrel_scope"],
            "generation_calls": 0,
            "embedding_calls": embedding_calls,
            "storage_identity": "v004",
            "citation_identity": "v003",
            "embedding_cache_sha256": hashlib.sha256(
                cache_path.read_bytes()
            ).hexdigest(),
            "baseline_replay_verified": True,
            "latency_ms": {
                "median": statistics.median(timing),
                "max": max(timing),
                "scope": (
                    "embedding (cached across strategies) plus diagnostic query; "
                    "excludes runtime replay, not E2E"
                ),
            },
            "summary": summarize(rows),
            "by_split": {
                s: summarize([r for r in rows if r["split"] == s])
                for s in ("development", "holdout")
            },
            "cases": rows,
            "not_executed": [
                "human_label_review",
                "answer_grounding",
                "browser_e2e",
                "production_activation",
            ],
        }
    finally:
        await retriever.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "evals/rag/cases-v1.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-variants", action="store_true")
    args = parser.parse_args()
    try:

        async def bounded_evaluate():
            return await asyncio.wait_for(evaluate(args), timeout=900)

        report = asyncio.run(bounded_evaluate())
    except Exception as exc:
        # No provider messages, endpoints, queries, Settings or traceback with secrets.
        print(json.dumps({"status": "FAILED", "failure_type": type(exc).__name__}))
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "COMPLETED", "summary": report["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
