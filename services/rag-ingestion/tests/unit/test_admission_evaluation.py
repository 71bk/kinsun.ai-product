"""Synthetic offline tests; no provider, dotenv or application factory imports."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts/rag"))

import admission_quality as quality  # noqa: E402


def candidate(key, score=0.9, vector=0.6, gate="PASS"):
    return {
        "chunk_id": key,
        "score": score,
        "raw_vector_score": vector,
        "raw_lexical_score": 0.0,
        "gate": gate,
    }


@pytest.fixture
def bundle():
    cases = [quality.load_dataset()[i] for i in (0, 2)]
    corpus = quality.load_corpus()
    trials = []
    for case in cases:
        anchor = next(iter(quality.evidence_anchors(case, corpus)))
        keys = [anchor] + [k for k in corpus if k != anchor][:2]
        rows = [candidate(k) for k in keys]
        result = quality.replay(rows, quality.BASELINE)
        for audience in quality.AUDIENCES:
            trials.append(
                {
                    "case_id": case["id"],
                    "audience": audience,
                    "candidates": rows,
                    "runtime_search_ids": result["post_floor_ids"],
                    "runtime_final_ids": result["final_ids"],
                }
            )
    snapshot = {
        "schema_version": "1.0",
        "mode": "READ_ONLY_ADMISSION_SNAPSHOT",
        "manifest": {
            "input_sha256": {
                "evals/rag/cases-v1.json": quality.sha256(ROOT / "evals/rag/cases-v1.json")
            }
        },
        "case_binding": quality.canonical_hash(cases),
        "trials": trials,
    }
    return cases, snapshot, quality.build_review(snapshot, cases, "synthetic-snapshot")


def test_dataset_groups_stay_together_and_new_samples_are_not_called_independent():
    cases = quality.load_dataset()
    assert len(cases) == 44
    assert sum(bool(c["draft_no_answer_reason"]) for c in cases) == 12
    for group in {c["group"] for c in cases}:
        assert len({c["split"] for c in cases if c["group"] == group}) == 1
    assert {c["origin"] for c in cases} == {
        "existing_regression",
        "same_author_synthetic_challenge",
    }


def test_admission_is_separate_from_ranking_and_minimum_remains_three():
    rows = [
        candidate("relative-high", vector=0.1),
        candidate("absolute-low-rank", score=0.6, vector=0.8),
    ]
    result = quality.replay(rows, quality.BASELINE)
    assert result["governed_ids"] == ["relative-high", "absolute-low-rank"]
    assert result["status"] == "INSUFFICIENT" and result["final_ids"] == []
    raw = next(p for p in quality.POLICIES if p["id"] == "raw_v0.70_l0.70")
    assert quality.replay(rows, raw)["governed_ids"] == ["absolute-low-rank"]
    rows += [candidate("denied", gate="BLOCKED")]
    assert quality.replay(rows, quality.BASELINE)["final_ids"] == []


def test_invalid_citation_fails_closed_until_five_valid_results_have_been_selected():
    rows = [candidate(f"{i:02}") for i in range(7)]
    rows[3]["gate"] = "INVALID_CITATION"
    assert quality.replay(rows, quality.BASELINE)["status"] == "INVALID_CITATION"
    rows[3]["gate"] = "PASS"
    rows[6]["gate"] = "INVALID_CITATION"
    assert quality.replay(rows, quality.BASELINE)["final_ids"] == [f"{i:02}" for i in range(5)]


@pytest.mark.parametrize("problem", ["duplicate", "missing", "nan", "baseline", "binding", "hash"])
def test_snapshot_rejects_incomplete_or_corrupt_replays(bundle, problem):
    cases, snapshot, _ = copy.deepcopy(bundle)
    if problem == "duplicate":
        snapshot["trials"].append(snapshot["trials"][0])
    elif problem == "missing":
        snapshot["trials"].pop()
    elif problem == "nan":
        snapshot["trials"][0]["candidates"][0]["score"] = float("nan")
    elif problem == "baseline":
        snapshot["trials"][0]["runtime_final_ids"] = []
    elif problem == "binding":
        snapshot["case_binding"] = "changed"
    else:
        snapshot["manifest"]["input_sha256"]["evals/rag/cases-v1.json"] = "0" * 64
    with pytest.raises(ValueError):
        quality.validate_snapshot(snapshot, cases)


def test_draft_labels_never_become_reviewed_metrics_and_holdout_is_not_swept(bundle):
    cases, snapshot, packet = bundle
    report = quality.evaluate(snapshot, packet, cases, "synthetic-snapshot")
    summary = report["development"]["runtime_baseline"]["all"]
    assert summary["reviewed_trials"] == 0
    assert summary["reviewed_false_acceptance"]["value"] is None
    assert summary["reviewed_pooled_ndcg_at_5"] is None
    assert report["selection"]["policy"] is None
    assert {r["policy"] for r in report["trials"] if r["split"] == "holdout"} == {
        "runtime_baseline"
    }


def test_human_review_requires_complete_grades_and_explicit_sufficient_sets(bundle):
    cases, snapshot, packet = bundle
    row = packet["reviews"][0]
    reviewed = row["audience_reviews"]["elder"]
    reviewed.update(
        status="REVIEWED",
        reviewer="synthetic-unit-test-reviewer",
        reviewed_at="2026-10-01T00:00:00+00:00",
        answerable=True,
        rationale="Synthetic unit fixture only",
    )
    with pytest.raises(ValueError, match="whole pool"):
        quality.validate_review(packet, snapshot, cases, "synthetic-snapshot")
    anchor = next(iter(quality.evidence_anchors(cases[0], quality.load_corpus())))
    for key, judgment in row["qrels"].items():
        judgment["grade"] = 3 if key == anchor else 0
    with pytest.raises(ValueError, match="sufficient"):
        quality.validate_review(packet, snapshot, cases, "synthetic-snapshot")
    reviewed["sufficient_sets"] = [[anchor]]
    report = quality.evaluate(snapshot, packet, cases, "synthetic-snapshot")
    summary = report["development"]["runtime_baseline"]["by_audience"]["elder"]
    assert summary["reviewed_trials"] == 1
    assert summary["reviewed_missed_answer"] == {"numerator": 0, "denominator": 1, "value": 0}
    assert summary["reviewed_pooled_recall_at_5"] == 1
    reviewed["sufficient_sets"] = [["not-in-pool"]]
    with pytest.raises(ValueError, match="supporting grades"):
        quality.validate_review(packet, snapshot, cases, "synthetic-snapshot")


def test_review_binding_evidence_pool_and_grade_integrity(bundle):
    cases, snapshot, packet = bundle
    for field, replacement in (("snapshot_sha256", "other"), ("evidence", {})):
        changed = {**packet, field: replacement}
        with pytest.raises(ValueError):
            quality.validate_review(changed, snapshot, cases, "synthetic-snapshot")
    first = next(iter(packet["reviews"][0]["qrels"].values()))
    first["grade"] = True
    with pytest.raises(ValueError, match="graded"):
        quality.validate_review(packet, snapshot, cases, "synthetic-snapshot")


def test_outputs_refuse_overwrite(tmp_path):
    output = tmp_path / "review.json"
    quality.write_new(output, {"synthetic": True})
    with pytest.raises(FileExistsError):
        quality.write_new(output, {"synthetic": False})


def test_committed_capture_review_and_comparison_reproduce_offline():
    snapshot_path = ROOT / "evals/rag/reports/admission-snapshot-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    packet = json.loads(
        (ROOT / "evals/rag/review/admission-review-v1.json").read_text(encoding="utf-8")
    )
    saved = json.loads(
        (ROOT / "evals/rag/reports/admission-comparison-v1.json").read_text(encoding="utf-8")
    )
    cases = quality.load_dataset()
    fresh = quality.evaluate(snapshot, packet, cases, quality.sha256(snapshot_path))
    for key, value in fresh.items():
        assert saved[key] == value
    assert len(snapshot["trials"]) == snapshot["baseline_verified_trials"] == 176
    assert sum(r["previous_miss_stage"] is not None for r in packet["reviews"]) == 16
    assert all(j["grade"] is None for r in packet["reviews"] for j in r["qrels"].values())
    # Replay checks captured outcomes and input data above. Implementation
    # digests describe the historical capture; current code is tested directly
    # and no longer needs a successor audit inventory for this replay to pass.
