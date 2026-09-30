"""Reproducible synthetic routing evaluation and source-grounded evidence inventory.

Run from the repository root with either service's Python. No dotenv, network,
provider or application Settings are loaded by the offline command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/core-api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.knowledge_router import route_knowledge  # noqa: E402
from quality_metrics import route_metrics  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path) -> tuple[dict, list[dict]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("data_classification") != "SYNTHETIC_PUBLIC_ONLY":
        raise ValueError("Only explicitly synthetic public evaluation data is accepted")
    cases, groups, queries = [], set(), set()
    for ordinal, group in enumerate(document["groups"]):
        if group["id"] in groups or group["purpose"] not in {
            "BASIC_VOICE",
            "general_information",
            "legal_reference",
        }:
            raise ValueError("Duplicate group or invalid expected purpose")
        groups.add(group["id"])
        for variant, query in enumerate(group["queries"]):
            if (
                not isinstance(query, str)
                or not 1 <= len(query) <= 2000
                or query in queries
            ):
                raise ValueError("Invalid or duplicate synthetic query")
            queries.add(query)
            cases.append(
                {
                    **group,
                    "case_id": f"{group['id']}-{variant + 1}",
                    "query": query,
                    "split": "holdout" if ordinal % 3 == 2 else "development",
                }
            )
    return document, cases


def load_corpus() -> dict[str, dict]:
    result = {}
    for path in sorted((ROOT / "data/rag-v2/candidates/v004/chunks").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                result[row["identity"]["chunk_id"]] = row
    if len(result) != 726:
        raise ValueError("Pinned v004 corpus count mismatch")
    return result


def evidence_anchors(case: dict, corpus: dict[str, dict]) -> dict[str, int]:
    result = {}
    for article in case.get("law_articles", []):
        matches = [
            key
            for key, row in corpus.items()
            if row["identity"]["source_id"]
            == "moj_long_term_care_services_act_20210609"
            and row["citation"]["source_locator"].endswith(f"／第 {article} 條")
        ]
        if len(matches) != 1:
            raise ValueError("Evidence locator is not unique")
        result[matches[0]] = 3
    # These are coverage probes, not relevance labels: a document's first chunk
    # cannot be assumed to answer an arbitrary question about that document.
    return result


def manifest(dataset: Path) -> dict:
    files = [
        dataset,
        ROOT / "config/rag/embedding-google.yaml",
        ROOT / "config/rag/hybrid-natural-language.json",
        ROOT / "config/rag/hybrid-legal.json",
        ROOT / "data/rag-v2/candidates/v004/SHA256SUMS.txt",
        ROOT
        / "data/rag-v3/governance/source-family-policy/runtime/candidates/v004"
        / "source-family-runtime-policy.json",
    ]
    commit = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    implementation = [
        "services/core-api/app/services/knowledge_router.py",
        "services/agent-runtime/src/agent_runtime/rag/query_normalization.py",
        "services/agent-runtime/src/agent_runtime/rag/postgres_backend.py",
        "services/agent-runtime/src/agent_runtime/rag/retriever.py",
        "scripts/rag/evaluate_quality.py",
        "scripts/rag/evaluate_live_quality.py",
        "scripts/rag/quality_metrics.py",
        "scripts/rag/quality_search.py",
        "services/core-api/uv.lock",
        "services/agent-runtime/uv.lock",
    ]
    return {
        "git_commit": commit,
        "input_sha256": {p.relative_to(ROOT).as_posix(): sha256(p) for p in files},
        "implementation_sha256": {p: sha256(ROOT / p) for p in implementation},
        "python_version": sys.version.split()[0],
        "router_sha256": sha256(
            ROOT / "services/core-api/app/services/knowledge_router.py"
        ),
        "storage_release": "rag-v2-v004-f3339ceae77c",
        "runtime_policy_version": "v004",
        "embedding_profile": "ep-google-00a12ec45096fa9d97d9e9b6",
        "judgments": "SOURCE_GROUNDED_DRAFT_REQUIRES_HUMAN_REVIEW",
        "production_approved": False,
    }


def evaluate_routes(cases: list[dict]) -> dict:
    results = {}
    for name, enabled in (("baseline", False), ("candidate", True)):
        rows = []
        for case in cases:
            decision = route_knowledge(case["query"], enabled=enabled)
            rows.append(
                {
                    "case_id": case["case_id"],
                    "group": case["id"],
                    "category": case["category"],
                    "split": case["split"],
                    "expected": case["purpose"],
                    "actual": decision.purpose,
                    "reason_code": decision.reason_code,
                }
            )
        results[name] = {
            "overall": route_metrics(rows),
            "by_split": {
                s: route_metrics([r for r in rows if r["split"] == s])
                for s in ("development", "holdout")
            },
            "by_category": {
                c: route_metrics([r for r in rows if r["category"] == c])
                for c in sorted({r["category"] for r in rows})
            },
            "cases": rows,
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=ROOT / "evals/rag/cases-v1.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document, cases = load_cases(args.dataset)
    corpus = load_corpus()
    anchors = {case["case_id"]: evidence_anchors(case, corpus) for case in cases}
    report = {
        "schema_version": "1.0",
        "mode": "OFFLINE_ROUTING_ONLY",
        "manifest": manifest(args.dataset),
        "case_count": len(cases),
        "group_count": len(document["groups"]),
        "qrel_scope": document["qrel_scope"],
        "routes": evaluate_routes(cases),
        "anchor_labeled_cases": sum(bool(x) for x in anchors.values()),
        "not_executed": [
            "live_retrieval",
            "answer_grounding",
            "human_label_review",
            "browser_e2e",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case_count": len(cases),
                "group_count": len(document["groups"]),
                "routing": {k: v["overall"] for k, v in report["routes"].items()},
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
