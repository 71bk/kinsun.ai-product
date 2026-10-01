"""Offline admission experiments and review packets; never imported by runtime."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path

from evaluate_quality import ROOT, evidence_anchors, load_cases, load_corpus, sha256
from quality_metrics import ranking_metrics, ratio

AUDIENCES = ("elder", "family_caregiver", "care_professional", "system_admin")
DATASET = ROOT / "evals/rag/admission-cases-v1.json"
BASELINE = {
    "id": "runtime_baseline",
    "hybrid_floor": 0.7,
    "vector_floor": 0.7,
    "lexical_floor": 0.7,
}
POLICIES = [BASELINE] + [
    {
        "id": f"raw_v{v:.2f}_l{lexical:.2f}",
        "hybrid_floor": None,
        "vector_floor": v,
        "lexical_floor": lexical,
    }
    for v in (0.50, 0.60, 0.70, 0.80)
    for lexical in (0.5, 0.7)
]


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def write_new(path: Path, value):
    """No silent overwrite of snapshots, review work or reports."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def load_dataset(path=DATASET):
    doc = json.loads(path.read_text(encoding="utf-8"))
    if (
        doc.get("data_classification") != "SYNTHETIC_PUBLIC_ONLY"
        or doc.get("independent_test_set") is not False
    ):
        raise ValueError(
            "This dataset must be explicitly synthetic and not independent"
        )
    _, old = load_cases(ROOT / "evals/rag/cases-v1.json")
    cases = [
        {
            "id": c["case_id"],
            "group": c["id"],
            "query": c["query"],
            "split": c["split"],
            "purpose": c["purpose"],
            "law_articles": c.get("law_articles", []),
            "origin": "existing_regression",
            "draft_no_answer_reason": None,
        }
        for c in old
        if c["purpose"] != "BASIC_VOICE" and c["case_id"].endswith("-1")
    ]
    groups = {c["group"]: c for c in cases}
    for extra in doc["additional_cases"]:
        parent = groups.get(extra["group"])
        split = parent["split"] if parent else extra["split"]
        if extra.get("split", split) != split:
            raise ValueError("Semantic group split leakage")
        cases.append(
            {
                "purpose": parent["purpose"] if parent else "general_information",
                "law_articles": [],
                "draft_no_answer_reason": None,
                **extra,
                "split": split,
                "origin": "same_author_synthetic_challenge",
            }
        )
    ids, queries, splits = set(), set(), {}
    for case in cases:
        if (
            case["id"] in ids
            or case["query"] in queries
            or not 1 <= len(case["query"]) <= 2000
        ):
            raise ValueError("Duplicate or invalid case")
        if case["split"] not in {"development", "holdout"} or case["purpose"] not in {
            "general_information",
            "legal_reference",
        }:
            raise ValueError("Invalid split or purpose")
        if splits.setdefault(case["group"], case["split"]) != case["split"]:
            raise ValueError("Semantic group split leakage")
        ids.add(case["id"])
        queries.add(case["query"])
    if not 1 <= len(cases) <= 64:
        raise ValueError("Case bound exceeded")
    return cases


def replay(rows, policy):
    """Keep Hybrid ordering, 50 search results and 3–5 citations fixed."""
    selected = sorted(
        (
            r
            for r in rows
            if (
                (
                    policy["hybrid_floor"] is not None
                    and r["score"] >= policy["hybrid_floor"]
                )
                or r["raw_vector_score"] >= policy["vector_floor"]
                or r["raw_lexical_score"] >= policy["lexical_floor"]
            )
        ),
        key=lambda r: (-r["score"], r["chunk_id"]),
    )[:50]
    governed, invalid = [], False
    for row in selected:
        if row["gate"] == "INVALID_CITATION":
            invalid = True
            break
        if row["gate"] == "PASS":
            governed.append(row["chunk_id"])
        if len(governed) == 5:
            break
    status = (
        "INVALID_CITATION"
        if invalid
        else "NO_DATA"
        if not governed
        else "INSUFFICIENT"
        if len(governed) < 3
        else "SUCCESS"
    )
    return {
        "status": status,
        "post_floor_ids": [r["chunk_id"] for r in selected],
        "governed_ids": [] if invalid else governed,
        "final_ids": governed if status == "SUCCESS" else [],
    }


def validate_snapshot(snapshot, cases):
    if (
        snapshot.get("schema_version") != "1.0"
        or snapshot.get("mode") != "READ_ONLY_ADMISSION_SNAPSHOT"
    ):
        raise ValueError("Invalid snapshot type")
    if snapshot.get("case_binding") != canonical_hash(cases):
        raise ValueError("Snapshot case binding mismatch")
    for path, digest in snapshot["manifest"]["input_sha256"].items():
        candidate = (ROOT / path).resolve()
        if not candidate.is_relative_to(ROOT) or sha256(candidate) != digest:
            raise ValueError("Snapshot input bytes changed")
    expected = {(c["id"], a) for c in cases for a in AUDIENCES}
    seen = set()
    for trial in snapshot["trials"]:
        key = (trial["case_id"], trial["audience"])
        if key not in expected or key in seen:
            raise ValueError("Unexpected or duplicate audience trial")
        seen.add(key)
        rows = trial["candidates"]
        if len(rows) > 100 or len({r["chunk_id"] for r in rows}) != len(rows):
            raise ValueError("Invalid candidate bound or duplicates")
        for row in rows:
            if row["gate"] not in {"PASS", "BLOCKED", "INVALID_CITATION"}:
                raise ValueError("Invalid governance state")
            for field in ("score", "raw_vector_score", "raw_lexical_score"):
                if type(row[field]) not in (int, float) or not math.isfinite(
                    row[field]
                ):
                    raise ValueError("Nonfinite candidate score")
        result = replay(rows, BASELINE)
        if (
            result["post_floor_ids"] != trial["runtime_search_ids"]
            or result["final_ids"] != trial["runtime_final_ids"]
        ):
            raise ValueError("Baseline does not match captured runtime")
    if seen != expected:
        raise ValueError("Missing audience trials")


def build_review(snapshot, cases, snapshot_sha):
    """Draft anchor suggestions never populate human grades or sufficient sets."""
    corpus = load_corpus()
    old_report = json.loads(
        (ROOT / "evals/rag/reports/live-retrieval-v1.json").read_text(encoding="utf-8")
    )
    misses = {
        r["case_id"]: r
        for r in old_report["cases"]
        if r["experiment"] == "original/hybrid" and r["anchors"]["recall"] == 0
    }
    reviews, evidence = [], {}
    for case in cases:
        trials = [t for t in snapshot["trials"] if t["case_id"] == case["id"]]
        anchors = evidence_anchors(case, corpus)
        pool = set(anchors).union(
            r["chunk_id"] for t in trials for r in t["candidates"]
        )
        for key in sorted(pool):
            chunk = corpus[key]
            evidence[key] = {
                "text": chunk["content"]["text"],
                "text_sha256": chunk["content"]["text_sha256"],
                "citation": chunk["citation"],
                "source_id": chunk["identity"]["source_id"],
            }
        previous = misses.get(case["id"])
        reviews.append(
            {
                "case_id": case["id"],
                "query": case["query"],
                "split": case["split"],
                "previous_miss_stage": None
                if previous is None
                else "score_floor"
                if previous["post_floor_anchor_recall"] == 0
                else "minimum_three",
                "draft_no_answer_reason": case["draft_no_answer_reason"],
                "qrels": {
                    key: {
                        "draft_anchor_grade": (
                            3 if case["purpose"] == "legal_reference" else 2
                        )
                        if key in anchors
                        else None,
                        "grade": None,
                    }
                    for key in sorted(pool)
                },
                "audience_reviews": {
                    a: {
                        "status": "PENDING",
                        "reviewer": None,
                        "reviewed_at": None,
                        "answerable": None,
                        "sufficient_sets": [],
                        "rationale": None,
                    }
                    for a in AUDIENCES
                },
            }
        )
    return {
        "schema_version": "1.0",
        "snapshot_sha256": snapshot_sha,
        "case_binding": canonical_hash(cases),
        "judgment_scope": "POOLED_CANDIDATES_PLUS_DRAFT_ANCHORS_NOT_EXHAUSTIVE_CORPUS",
        "independent_test_set": False,
        "evidence": evidence,
        "reviews": reviews,
    }


def validate_review(packet, snapshot, cases, snapshot_sha):
    if packet.get("snapshot_sha256") != snapshot_sha or packet.get(
        "case_binding"
    ) != canonical_hash(cases):
        raise ValueError("Review binding mismatch")
    expected = build_review(snapshot, cases, snapshot_sha)
    if packet.get("evidence") != expected["evidence"]:
        raise ValueError("Review evidence differs from pinned corpus")
    by_id = {r["case_id"]: r for r in packet["reviews"]}
    if len(by_id) != len(packet["reviews"]) or set(by_id) != {c["id"] for c in cases}:
        raise ValueError("Review cases missing or duplicated")
    for base in expected["reviews"]:
        row = by_id[base["case_id"]]
        for key in ("query", "split", "previous_miss_stage", "draft_no_answer_reason"):
            if row[key] != base[key]:
                raise ValueError("Review case metadata changed")
        if set(row["qrels"]) != set(base["qrels"]) or set(
            row["audience_reviews"]
        ) != set(AUDIENCES):
            raise ValueError("Incomplete judgment pool or audiences")
        for key, judgment in row["qrels"].items():
            grade = judgment["grade"]
            if grade is not None and (type(grade) is not int or grade not in range(4)):
                raise ValueError("Invalid graded judgment")
            if (
                judgment["draft_anchor_grade"]
                != base["qrels"][key]["draft_anchor_grade"]
            ):
                raise ValueError("Draft provenance changed")
        for audience, review in row["audience_reviews"].items():
            if review["status"] not in {"PENDING", "REVIEWED"}:
                raise ValueError("Invalid review status")
            if review["status"] == "PENDING":
                continue
            if any(
                not isinstance(review.get(k), str) or not review[k].strip()
                for k in ("reviewer", "reviewed_at", "rationale")
            ):
                raise ValueError(
                    "Reviewed judgments require human attribution and rationale"
                )
            if type(review["answerable"]) is not bool or any(
                j["grade"] is None for j in row["qrels"].values()
            ):
                raise ValueError("Reviewed judgments must cover the whole pool")
            if datetime.fromisoformat(review["reviewed_at"]).tzinfo is None:
                raise ValueError("Review timestamp requires timezone")
            sets = review["sufficient_sets"]
            if not isinstance(sets, list) or bool(sets) != review["answerable"]:
                raise ValueError(
                    "Answerability requires explicit sufficient evidence sets"
                )
            for group in sets:
                if (
                    not isinstance(group, list)
                    or not 1 <= len(group) <= 5
                    or len(set(group)) != len(group)
                ):
                    raise ValueError("Invalid sufficient evidence set")
                if any(
                    k not in row["qrels"] or row["qrels"][k]["grade"] < 2 for k in group
                ):
                    raise ValueError(
                        "Sufficient evidence must have reviewed supporting grades"
                    )
    return by_id


def summarize(rows):
    reviewed = [r for r in rows if r["reviewed"]]
    positive = [r for r in reviewed if r["answerable"]]
    negative = [r for r in reviewed if not r["answerable"]]
    anchors = [
        r["draft_anchor_recall"] for r in rows if r["draft_anchor_recall"] is not None
    ]
    probes = [r for r in rows if r["draft_negative"]]
    ranked = [
        r["reviewed_ranking"]
        for r in reviewed
        if r["reviewed_ranking"]["recall"] is not None
    ]
    return {
        "trial_count": len(rows),
        "status_counts": dict(Counter(r["status"] for r in rows)),
        "draft_anchor_recall_at_5": sum(anchors) / len(anchors) if anchors else None,
        "draft_negative_acceptance": ratio(
            sum(bool(r["final_ids"]) for r in probes), len(probes)
        ),
        "reviewed_trials": len(reviewed),
        "reviewed_pooled_recall_at_5": sum(r["recall"] for r in ranked) / len(ranked)
        if ranked
        else None,
        "reviewed_pooled_ndcg_at_5": sum(r["ndcg"] for r in ranked) / len(ranked)
        if ranked
        else None,
        "reviewed_missed_answer": ratio(
            sum(not r["sufficient"] for r in positive), len(positive)
        ),
        "reviewed_false_acceptance": ratio(
            sum(bool(r["final_ids"]) for r in negative), len(negative)
        ),
        "reviewed_insufficient_acceptance": ratio(
            sum(bool(r["final_ids"]) and not r["sufficient"] for r in reviewed),
            sum(bool(r["final_ids"]) for r in reviewed),
        ),
        "one_or_two_governed_count_only_opportunities": sum(
            r["status"] == "INSUFFICIENT" for r in rows
        ),
    }


def evaluate(snapshot, packet, cases, snapshot_sha):
    validate_snapshot(snapshot, cases)
    reviews = validate_review(packet, snapshot, cases, snapshot_sha)
    by_id, corpus = {c["id"]: c for c in cases}, load_corpus()
    rows = []
    for trial in snapshot["trials"]:
        case = by_id[trial["case_id"]]
        judgment = reviews[case["id"]]
        review = judgment["audience_reviews"][trial["audience"]]
        for policy in POLICIES if case["split"] == "development" else [BASELINE]:
            result = replay(trial["candidates"], policy)
            reviewed = review["status"] == "REVIEWED"
            sufficient = (
                any(
                    set(group).issubset(result["final_ids"])
                    for group in review["sufficient_sets"]
                )
                if reviewed
                else None
            )
            rows.append(
                {
                    "case_id": case["id"],
                    "group": case["group"],
                    "split": case["split"],
                    "audience": trial["audience"],
                    "policy": policy["id"],
                    **result,
                    "draft_anchor_recall": ranking_metrics(
                        result["final_ids"], evidence_anchors(case, corpus)
                    )["recall"],
                    "draft_negative": bool(case["draft_no_answer_reason"]),
                    "reviewed": reviewed,
                    "answerable": review["answerable"] if reviewed else None,
                    "sufficient": sufficient,
                    "reviewed_ranking": ranking_metrics(
                        result["final_ids"],
                        {k: j["grade"] for k, j in judgment["qrels"].items()},
                    )
                    if reviewed
                    else None,
                }
            )

    def summary(subset):
        return {
            "all": summarize(subset),
            "by_audience": {
                a: summarize([r for r in subset if r["audience"] == a])
                for a in AUDIENCES
            },
        }

    return {
        "schema_version": "1.0",
        "mode": "OFFLINE_ADMISSION_CALIBRATION",
        "snapshot_sha256": snapshot_sha,
        "review_sha256": canonical_hash(packet),
        "policy_grid": POLICIES,
        "ranking": "UNCHANGED_HYBRID",
        "minimum_citations": 3,
        "development": {
            p["id"]: summary(
                [
                    r
                    for r in rows
                    if r["split"] == "development" and r["policy"] == p["id"]
                ]
            )
            for p in POLICIES
        },
        "holdout_baseline_only": summary([r for r in rows if r["split"] == "holdout"]),
        "selection": {
            "policy": None,
            "status": "REQUIRES_HUMAN_REVIEW_AND_INDEPENDENT_VALIDATION",
            "production_approved": False,
        },
        "limitations": [
            "Draft anchor recall is not answer accuracy",
            "No unjudged candidate is treated as irrelevant",
            "Minimum-count opportunities do not prove sufficiency",
            "Four audience trials per query are correlated",
            "Retrieval is force-probed; private/absent-answer probes do not measure the routed application",
            "No generation or end-to-end latency measured",
            "Holdout was not swept; independent authored data is still required",
        ],
        "trials": rows,
    }
