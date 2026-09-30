"""Offline CI regression gates for synthetic routing and evidence-anchor metrics."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts/rag"))

from evaluate_quality import (  # noqa: E402
    evaluate_routes,
    evidence_anchors,
    load_cases,
    load_corpus,
)
from quality_metrics import ranking_metrics  # noqa: E402


def test_routing_dataset_has_grouped_holdout_and_improves_baseline():
    document, cases = load_cases(ROOT / "evals/rag/cases-v1.json")
    assert len(cases) == 120 and len(document["groups"]) == 40
    for group in document["groups"]:
        assert len({c["split"] for c in cases if c["id"] == group["id"]}) == 1
    result = evaluate_routes(cases)
    for split in ("development", "holdout"):
        score = result["candidate"]["by_split"][split]
        assert score["accuracy"]["value"] >= 0.90
        assert score["knowledge_recall"]["value"] >= 0.95
        assert score["nonknowledge_false_positive"]["value"] <= 0.05
    assert (
        result["candidate"]["overall"]["accuracy"]["value"]
        > result["baseline"]["overall"]["accuracy"]["value"]
    )


def test_evidence_anchors_resolve_to_unique_pinned_source_locators():
    _, cases = load_cases(ROOT / "evals/rag/cases-v1.json")
    corpus = load_corpus()
    for case in cases:
        anchors = evidence_anchors(case, corpus)
        assert len(anchors) == len(case.get("law_articles", []))
        assert all(key in corpus for key in anchors)
        if case["purpose"] == "BASIC_VOICE":
            assert not anchors


def test_duplicate_queries_and_non_synthetic_inputs_are_rejected(tmp_path):
    path = tmp_path / "cases.json"
    doc = {
        "data_classification": "SYNTHETIC_PUBLIC_ONLY",
        "groups": [{"id": "x", "purpose": "BASIC_VOICE", "queries": ["synthetic", "synthetic"]}],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)
    doc["data_classification"] = "PRIVATE"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases(path)


def test_metrics_count_missed_evidence_and_do_not_reward_duplicate_results():
    qrels = {"a": 3, "b": 2}
    perfect = ranking_metrics(["a", "b"], qrels)
    duplicate = ranking_metrics(["a", "a"], qrels)
    assert perfect["recall"] == perfect["ndcg"] == 1
    assert duplicate["recall"] == 0.5 and duplicate["ndcg"] < 1
    assert ranking_metrics([], qrels)["recall"] == 0
    assert ranking_metrics(["a"], {})["recall"] is None
    assert ranking_metrics(["a"], {"a": 0})["ndcg"] is None


@pytest.mark.parametrize(
    "qrels,k", [({"a": -1}, 5), ({"a": True}, 5), ({"a": 4}, 5), ({"a": 3}, 0)]
)
def test_metrics_reject_invalid_judgments(qrels, k):
    with pytest.raises(ValueError):
        ranking_metrics(["a"], qrels, k)
