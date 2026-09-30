"""Offline, dependency-free metrics with explicit denominators and no-data semantics."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence


def ranking_metrics(
    ranked_ids: Sequence[str], judgments: Mapping[str, int], k: int = 5
) -> dict:
    """Empty judgments are unscored, not a perfect or failed relevance result.

    This computes recall against the supplied judgments. Callers must disclose
    whether they are exhaustive judgments or only evidence anchors.
    """
    if k < 1 or any(
        type(v) is not int or v not in (0, 1, 2, 3) for v in judgments.values()
    ):
        raise ValueError("Invalid ranking evaluation inputs")
    relevant = {key for key, grade in judgments.items() if grade > 0}
    if not relevant:
        return {"recall": None, "ndcg": None, "hit": None, "relevant_count": 0}
    unique = list(dict.fromkeys(ranked_ids))[:k]
    dcg = sum(
        (2 ** judgments.get(key, 0) - 1) / math.log2(i + 2)
        for i, key in enumerate(unique)
    )
    ideal = sum(
        (2**grade - 1) / math.log2(i + 2)
        for i, grade in enumerate(sorted(judgments.values(), reverse=True)[:k])
    )
    found = len(relevant.intersection(unique))
    return {
        "recall": found / len(relevant),
        "ndcg": dcg / ideal,
        "hit": int(found > 0),
        "relevant_count": len(relevant),
    }


def ratio(numerator: int, denominator: int) -> dict:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def route_metrics(rows: Sequence[Mapping]) -> dict:
    positives = [r for r in rows if r["expected"] != "BASIC_VOICE"]
    negatives = [r for r in rows if r["expected"] == "BASIC_VOICE"]
    return {
        "accuracy": ratio(sum(r["expected"] == r["actual"] for r in rows), len(rows)),
        "knowledge_recall": ratio(
            sum(r["actual"] != "BASIC_VOICE" for r in positives), len(positives)
        ),
        "nonknowledge_false_positive": ratio(
            sum(r["actual"] != "BASIC_VOICE" for r in negatives), len(negatives)
        ),
        "confusion": dict(Counter(f"{r['expected']} -> {r['actual']}" for r in rows)),
    }
