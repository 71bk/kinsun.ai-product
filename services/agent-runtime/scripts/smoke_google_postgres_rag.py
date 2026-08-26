"""Run a synthetic Google-query-embedding to PostgreSQL RAG smoke test."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import SecretStr

from agent_runtime.rag.models import RagRuntimeSettings, RetrievalRequestV2
from agent_runtime.rag.retriever import build_retriever

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONFIG_ROOT = REPOSITORY_ROOT / "config" / "rag"


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _run() -> None:
    if os.environ.get("RAG_SEARCH_BACKEND", "").casefold() != "postgresql":
        raise RuntimeError("RAG_SEARCH_BACKEND must be postgresql")
    if os.environ.get("RAG_ALLOW_NEEDS_REVIEW_CITATIONS", "").casefold() != "true":
        raise RuntimeError("staging smoke requires the explicit needs-review override")
    google_api_key = _required_environment("GEMINI_API_KEY")
    settings = RagRuntimeSettings.from_config_files(
        embedding_config_path=CONFIG_ROOT / "embedding-google.yaml",
        index_config_path=CONFIG_ROOT / "opensearch-index-v1.json",
        natural_profile_path=CONFIG_ROOT / "hybrid-natural-language.json",
        legal_profile_path=CONFIG_ROOT / "hybrid-legal.json",
        environ=os.environ,
        database_url=SecretStr(_required_environment("RAG_DATABASE_URL")),
    )
    audience = os.environ.get("RAG_SMOKE_AUDIENCE", "care_professional").strip()
    if audience != "care_professional" and not settings.allow_all_audiences:
        raise RuntimeError("non-professional smoke requires the staging audience override")
    retriever = build_retriever(
        settings,
        google_api_key=google_api_key,
        google_timeout_seconds=30.0,
    )
    request = RetrievalRequestV2(
        schema_version="2.0.0",
        request_id="synthetic-google-postgres-smoke",
        query="家庭照顧者有哪些評估與支持資源？",
        query_profile="natural_language",
        top_k=5,
        audience=audience,
        purpose="general_information",
        language="zh-TW",
    )
    try:
        response = await retriever.retrieve_v2(request)
    finally:
        await retriever.aclose()
    if response.status != "SUCCESS":
        raise RuntimeError(f"end-to-end retrieval returned {response.status}")
    if any(
        result.review_status != "needs_review" or result.production_approved
        for result in response.results
    ):
        raise RuntimeError("end-to-end retrieval crossed the staging governance boundary")
    chunk_ids = ",".join(result.chunk_id for result in response.results)
    print(
        f"google_postgres_smoke=PASS audience={audience} "
        f"hits={len(response.results)} ids={chunk_ids}"
    )


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except Exception as exc:
        print(f"google_postgres_smoke=FAIL error_type={type(exc).__name__}")
        raise SystemExit(1) from None
