"""Run a synthetic, read-only PostgreSQL RAG backend smoke test."""

from __future__ import annotations

import asyncio
import os

from pydantic import SecretStr

from agent_runtime.rag.models import (
    HybridSearchPlan,
    PostgresSearchSettings,
    QueryEmbeddingSettings,
)
from agent_runtime.rag.postgres_backend import build_postgres_search_backend


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _run() -> None:
    allow_needs_review = (
        os.environ.get(
            "RAG_ALLOW_NEEDS_REVIEW_CITATIONS",
            "false",
        ).casefold()
        == "true"
    )
    settings = PostgresSearchSettings(
        database_url=SecretStr(_required_environment("RAG_DATABASE_URL")),
        release_id=_required_environment("RAG_POSTGRES_RELEASE_ID"),
        embedding_profile_id=_required_environment("RAG_POSTGRES_EMBEDDING_PROFILE_ID"),
        mode="staging",
    )
    embedding = QueryEmbeddingSettings(
        provider="google",
        model_id=os.environ.get("GEMINI_EMBEDDING_MODEL_ID", "gemini-embedding-001"),
        dimension=1024,
    )
    backend = build_postgres_search_backend(settings, embedding)
    plan = HybridSearchPlan(
        query="家庭照顧者評估",
        query_vector=[0.01] * 1024,
        profile="natural_language",
        top_k=5,
        audience="care_professional",
        purpose="general_information",
        governed_citations=True,
        allow_needs_review=allow_needs_review,
        bm25_weight=0.4,
        vector_weight=0.6,
        # This smoke proves the SQL/data-plane path with a synthetic non-zero
        # vector. Retrieval-quality thresholds belong to the Google end-to-end
        # smoke and Golden Query evaluation, not this connectivity check.
        min_score=0.01,
    )
    try:
        hits = await backend.search(plan)
    finally:
        await backend.aclose()
    if not hits:
        raise RuntimeError("PostgreSQL RAG smoke returned no governed hits")
    chunk_ids = ",".join(str(hit.source.get("chunk_id")) for hit in hits)
    print(f"postgres_smoke=PASS hits={len(hits)} ids={chunk_ids}")


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"postgres_smoke=FAIL error_type={type(exc).__name__}")
        raise SystemExit(1) from None
