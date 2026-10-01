"""Capture a bounded read-only staging snapshot, then review/replay fully offline."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from admission_quality import (
    AUDIENCES,
    DATASET,
    ROOT,
    build_review,
    canonical_hash,
    evaluate,
    load_dataset,
    validate_snapshot,
    write_new,
)
from evaluate_quality import manifest, sha256


async def capture(dataset):
    # Provider/application imports are deliberately confined to explicit capture.
    sys.path.insert(0, str(ROOT / "services/agent-runtime/src"))
    from agent_runtime.app import build_configured_rag_retriever
    from agent_runtime.orchestration.rag_integration import _retrieval_query
    from agent_runtime.rag.models import HybridProfileSettings, RetrievalRequestV2
    from agent_runtime.rag.postgres_backend import PostgresSearchBackend

    from quality_search import candidates, governed_results, rank

    cases = load_dataset(dataset)
    pinned = manifest(dataset)
    for path in ("evals/rag/cases-v1.json", "evals/rag/reports/live-retrieval-v1.json"):
        pinned["input_sha256"][path] = sha256(ROOT / path)
    for path in (
        "scripts/rag/admission_quality.py",
        "scripts/rag/evaluate_admission.py",
    ):
        pinned["implementation_sha256"][path] = sha256(ROOT / path)
    retriever = build_configured_rag_retriever()
    if retriever is None:
        raise ValueError("Staging retriever unavailable")
    started = datetime.now(UTC).isoformat()
    trials, cache, embedding_calls, embedding_ms = [], {}, 0, 0.0
    binding = pinned["input_sha256"]["config/rag/embedding-google.yaml"]
    cache_path = ROOT / ".qa/rag-admission-embeddings-v1.json"
    try:
        backend, policy = retriever._search_backend, retriever._source_family_policy
        if (
            not isinstance(backend, PostgresSearchBackend)
            or backend._settings.release_id != pinned["storage_release"]
            or backend._settings.embedding_profile_id != pinned["embedding_profile"]
        ):
            raise ValueError("Pinned PostgreSQL release/profile required")
        policy_path = "data/rag-v3/governance/source-family-policy/runtime/candidates/v004/source-family-runtime-policy.json"
        if (
            policy is None
            or policy.sha256 != pinned["input_sha256"][policy_path]
            or retriever._allow_all_audiences
        ):
            raise ValueError("Pinned runtime policy required")
        embedding = backend._embedding_settings
        if (embedding.provider, embedding.model_id, embedding.dimension) != (
            "google",
            "gemini-embedding-001",
            1024,
        ):
            raise ValueError("Pinned embedding configuration required")
        for name, filename in (
            ("natural_language", "hybrid-natural-language.json"),
            ("legal", "hybrid-legal.json"),
        ):
            expected = HybridProfileSettings.from_config(
                json.loads((ROOT / "config/rag" / filename).read_text(encoding="utf-8"))
            )
            if retriever._hybrid_search._settings.for_profile(name) != expected:
                raise ValueError("Runtime profile differs from pinned configuration")
        citation_to_storage = {
            c.chunk_id: storage for storage, c in policy._by_prior_chunk_id.items()
        }
        for path in (ROOT / ".qa/rag-quality-embeddings-v1.json", cache_path):
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                if (
                    saved.get("binding") == binding
                    and saved.get("profile") == pinned["embedding_profile"]
                ):
                    cache.update(saved["vectors"])
        for case in cases:
            profile = (
                "legal" if case["purpose"] == "legal_reference" else "natural_language"
            )
            query = _retrieval_query(profile, case["query"])
            key = hashlib.sha256(query.encode("utf-8")).hexdigest()
            if key not in cache:
                before = time.perf_counter()
                cache[key] = await asyncio.wait_for(
                    retriever._embedding_provider.embed_query(query), timeout=35
                )
                embedding_ms += (time.perf_counter() - before) * 1000
                embedding_calls += 1
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(
                        {
                            "binding": binding,
                            "profile": pinned["embedding_profile"],
                            "vectors": cache,
                        },
                        allow_nan=False,
                    ),
                    encoding="utf-8",
                )
            vector = cache[key]
            if len(vector) != 1024 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in vector
            ):
                raise ValueError("Invalid cached vector")
            for audience in AUDIENCES:
                request = RetrievalRequestV2(
                    schema_version="2.0.0",
                    request_id=f"synthetic-{case['id']}-{audience}",
                    query=query,
                    query_profile=profile,
                    top_k=5,
                    audience=audience,
                    purpose=case["purpose"],
                    language="zh-TW",
                )
                plan = retriever._hybrid_search.build_v2(
                    request,
                    vector,
                    allow_needs_review=retriever._allow_needs_review_citations,
                    policy_candidate_chunk_ids=policy.candidate_chunk_ids,
                )
                before = time.perf_counter()
                rows = await asyncio.wait_for(candidates(backend, plan), timeout=35)
                query_ms = round((time.perf_counter() - before) * 1000, 2)
                selected = rank(rows, "hybrid", plan.min_score)
                actual = await asyncio.wait_for(backend.search(plan), timeout=35)
                actual_ids = [h.source["chunk_id"] for h in actual]
                if actual_ids != [r["chunk_id"] for r in selected]:
                    raise ValueError("Baseline candidate replay differs from runtime")
                governed = governed_results(selected, request, retriever)
                final = governed if governed is not None and len(governed) >= 3 else []
                compact = []
                for row in rows:
                    eligible = governed_results([row], request, retriever)
                    compact.append(
                        {
                            "chunk_id": row["chunk_id"],
                            **{
                                f: float(row[f])
                                for f in (
                                    "score",
                                    "raw_vector_score",
                                    "raw_lexical_score",
                                )
                            },
                            "gate": "INVALID_CITATION"
                            if eligible is None
                            else "PASS"
                            if eligible
                            else "BLOCKED",
                        }
                    )
                trials.append(
                    {
                        "case_id": case["id"],
                        "audience": audience,
                        "diagnostic_sql_ms": query_ms,
                        "candidates": compact,
                        "runtime_search_ids": actual_ids,
                        "runtime_final_ids": [
                            citation_to_storage[r.chunk_id] for r in final
                        ],
                    }
                )
            print(
                json.dumps(
                    {"completed_case": case["id"], "embedding_calls": embedding_calls}
                ),
                flush=True,
            )
        result = {
            "schema_version": "1.0",
            "mode": "READ_ONLY_ADMISSION_SNAPSHOT",
            "manifest": pinned,
            "case_binding": canonical_hash(cases),
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
            "embedding_calls": embedding_calls,
            "embedding_provider_ms": round(embedding_ms, 2),
            "generation_calls": 0,
            "database_writes": 0,
            "baseline_verified_trials": len(trials),
            "latency_scope": "Diagnostic SQL only; embedding time recorded separately; sequential transactions, not a single DB snapshot or E2E SLO",
            "trials": trials,
        }
        validate_snapshot(result, cases)
        return result
    finally:
        await retriever.aclose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "review", "compare"))
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; use a new versioned path")
    try:
        if args.command == "capture":

            async def bounded():
                return await asyncio.wait_for(capture(args.dataset), timeout=900)

            result = asyncio.run(bounded())
        else:
            if args.snapshot is None:
                parser.error("--snapshot required")
            cases = load_dataset(args.dataset)
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
            validate_snapshot(snapshot, cases)
            digest = sha256(args.snapshot)
            if args.command == "review":
                result = build_review(snapshot, cases, digest)
            else:
                if args.review is None:
                    parser.error("--review required")
                packet = json.loads(args.review.read_text(encoding="utf-8"))
                result = evaluate(snapshot, packet, cases, digest)
                result["implementation_sha256"] = {
                    p: sha256(ROOT / p)
                    for p in (
                        "scripts/rag/admission_quality.py",
                        "scripts/rag/evaluate_admission.py",
                        "scripts/rag/quality_metrics.py",
                    )
                }
        write_new(args.output, result)
    except Exception as exc:
        # Provider exceptions can contain endpoints/credentials; never echo messages.
        print(json.dumps({"status": "FAILED", "failure_type": type(exc).__name__}))
        return 1
    print(json.dumps({"status": "COMPLETED", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
