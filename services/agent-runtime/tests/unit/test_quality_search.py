import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts/rag"))

from quality_search import DIAGNOSTIC_SQL, rank  # noqa: E402

from agent_runtime.rag.postgres_backend import POSTGRES_HYBRID_SEARCH_SQL  # noqa: E402


def row(name, lexical, vector, raw_lexical, raw_vector, hybrid):
    return {
        "chunk_id": name,
        "lexical_score": lexical,
        "vector_score": vector,
        "raw_lexical_score": raw_lexical,
        "raw_vector_score": raw_vector,
        "score": hybrid,
    }


def test_diagnostics_preserve_entire_governance_and_both_candidate_legs():
    prefix = POSTGRES_HYBRID_SEARCH_SQL.split("fused AS (", 1)[0]
    assert DIAGNOSTIC_SQL.startswith(prefix)
    assert "LIMIT 100" in DIAGNOSTIC_SQL
    assert "FULL OUTER JOIN vector_normalized" in DIAGNOSTIC_SQL
    assert "CAST(:query AS text)" in DIAGNOSTIC_SQL


def test_rank_score_is_not_used_as_absolute_rrf_confidence():
    noise = row("noise", 1.0, 1.0, 0.1, 0.2, 1.0)
    assert len(rank([noise], "hybrid", 0.7)) == 1
    assert rank([noise], "raw_floor", 0.7) == []
    assert rank([noise], "rrf", 0.7) == []
    evidence = row("evidence", None, 1.0, 0.0, 0.8, 0.6)
    rrf = rank([evidence], "rrf", 0.7)
    assert rrf[0]["score"] == pytest.approx(1 / 61)
    assert rank([evidence], "lexical", 0.7) == []
    assert len(rank([evidence], "dense", 0.7)) == 1


def test_rrf_promotes_agreement_and_bounds_output():
    rows = [
        row("a", 1.0, None, 0.9, 0.0, 0.4),
        row("b", 0.5, 1.0, 0.8, 0.9, 0.8),
        row("c", None, 0.5, 0.0, 0.8, 0.3),
    ]
    assert [r["chunk_id"] for r in rank(rows, "rrf", 0.7)] == ["b", "a", "c"]
    many = [row(f"x{i:03}", 1.0, None, 1.0, 0.0, 1.0) for i in range(100)]
    assert len(rank(many, "hybrid", 0.7)) == 50
    assert rank(many[::-1], "hybrid", 0.7) == rank(many, "hybrid", 0.7)
    with pytest.raises(ValueError):
        rank(rows, "custom-sql", 0.7)
