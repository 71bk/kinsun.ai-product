"""Evaluation-only ranking replay over the runtime's two bounded retrieval legs.

Never imported by the application. Reuses all runtime SQL eligibility predicates,
keeps at most 50 candidates per leg / 100 in the union, and preserves the final
runtime policy/citation gate. Diagnostic candidates never enter Agent context.
"""

from __future__ import annotations

from sqlalchemy import text

from agent_runtime.rag.postgres_backend import (
    POSTGRES_HYBRID_SEARCH_SQL,
    PostgresSearchBackend,
    _to_search_hits,
)
from agent_runtime.rag.retriever import _eligible_unique_results_v2

STRATEGIES = ("hybrid", "lexical", "dense", "equal_weight", "raw_floor", "rrf")


def diagnostic_sql() -> str:
    prefix, _ = POSTGRES_HYBRID_SEARCH_SQL.split("fused AS (", 1)
    _, projection = POSTGRES_HYBRID_SEARCH_SQL.split("\nSELECT\n    ranked.score,", 1)
    # The shared projection includes public text for the final hash/citation gate.
    return (
        prefix
        + """ranked AS (
        SELECT coalesce(lexical.chunk_id, vector.chunk_id) AS chunk_id,
            coalesce(lexical.raw_score, 0.0) AS raw_lexical_score,
            coalesce(vector.raw_score, 0.0) AS raw_vector_score,
            lexical.normalized_score AS lexical_score,
            vector.normalized_score AS vector_score,
            CAST(:bm25_weight AS double precision) * coalesce(lexical.normalized_score, 0.0)
              + CAST(:vector_weight AS double precision)
                * coalesce(vector.normalized_score, 0.0) AS score
        FROM lexical_normalized AS lexical
        FULL OUTER JOIN vector_normalized AS vector USING (chunk_id)
        ORDER BY score DESC, chunk_id
        LIMIT 100
    )
    SELECT ranked.lexical_score, ranked.vector_score, ranked.score,"""
        + projection
    )


DIAGNOSTIC_SQL = diagnostic_sql()


async def candidates(backend: PostgresSearchBackend, plan) -> list[dict]:
    async with backend._engine.connect() as connection:
        # Also enforce read-only in this transaction when the principal has wider grants.
        await connection.execute(text("SET TRANSACTION READ ONLY"))
        result = await connection.execute(
            text(DIAGNOSTIC_SQL), backend._parameters(plan)
        )
        rows = [dict(row) for row in result.mappings().all()]
    if len(rows) > 100:
        raise ValueError("Diagnostic candidate bound exceeded")
    return rows


def rank(rows: list[dict], strategy: str, floor: float) -> list[dict]:
    if strategy not in STRATEGIES:
        raise ValueError("Unsupported ranking experiment")
    ranks = {}
    for leg in ("lexical", "vector"):
        members = sorted(
            (r for r in rows if r[f"{leg}_score"] is not None),
            key=lambda r: (-r[f"raw_{leg}_score"], r["chunk_id"]),
        )
        ranks[leg] = {r["chunk_id"]: i for i, r in enumerate(members, 1)}
    output = []
    for row in rows:
        lexical, vector = row["lexical_score"] or 0.0, row["vector_score"] or 0.0
        raw_pass = row["raw_lexical_score"] >= floor or row["raw_vector_score"] >= floor
        score = row["score"]
        if strategy in {"hybrid", "raw_floor"}:
            accept = raw_pass or (strategy == "hybrid" and score >= floor)
        elif strategy == "lexical":
            score = lexical
            accept = row["lexical_score"] is not None and (
                score >= floor or row["raw_lexical_score"] >= floor
            )
        elif strategy == "dense":
            score = vector
            accept = row["vector_score"] is not None and (
                score >= floor or row["raw_vector_score"] >= floor
            )
        elif strategy == "equal_weight":
            score = 0.5 * lexical + 0.5 * vector
            accept = raw_pass or score >= floor
        else:
            score = sum(
                1 / (60 + ranks[leg][row["chunk_id"]])
                for leg in ranks
                if row["chunk_id"] in ranks[leg]
            )
            # Rank scores are not confidence probabilities. Keep the existing raw
            # evidence floor instead of applying the 0.7 hybrid floor to RRF.
            accept = raw_pass
        if accept:
            output.append({**row, "score": float(score)})
    return sorted(output, key=lambda r: (-r["score"], r["chunk_id"]))[:50]


def governed_results(rows, request, retriever):
    return _eligible_unique_results_v2(
        _to_search_hits(rows),
        5,
        request.query_profile,
        audience=request.audience,
        purpose=request.purpose,
        allow_needs_review=retriever._allow_needs_review_citations,
        allow_all_audiences=False,
        source_family_policy=retriever._source_family_policy,
    )
