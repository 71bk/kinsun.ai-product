"""Verify one public Golden Query against the configured live staging retriever."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME_SOURCE = REPOSITORY_ROOT / "services" / "agent-runtime" / "src"
sys.path.insert(0, str(AGENT_RUNTIME_SOURCE))

from agent_runtime.app import build_configured_rag_retriever  # noqa: E402
from agent_runtime.rag.models import RetrievalRequestV2  # noqa: E402

QUERY = "長者平常要怎麼吃得比較均衡？"
NEGATIVE_QUERY = "請幫我寫一首關於火星殖民的科幻詩。"


def _request(query: str) -> RetrievalRequestV2:
    return RetrievalRequestV2(
        schema_version="2.0.0",
        request_id=str(uuid4()),
        query=query,
        query_profile="natural_language",
        top_k=5,
        audience="elder",
        purpose="general_information",
        language="zh-TW",
    )


async def _main() -> None:
    retriever = build_configured_rag_retriever()
    if retriever is None:
        raise RuntimeError("Configured RAG retriever is unavailable")
    try:
        response = await retriever.retrieve_v2(_request(QUERY))
        negative_response = await retriever.retrieve_v2(_request(NEGATIVE_QUERY))
    finally:
        await retriever.aclose()

    if response.status != "SUCCESS":
        raise RuntimeError(f"Live retrieval returned {response.status}")
    if not 3 <= len(response.results) <= 5:
        raise RuntimeError(
            "Live retrieval did not return a complete bounded result set"
        )
    if any(result.artifact_version != "v003" for result in response.results):
        raise RuntimeError("Live retrieval returned a non-v003 citation")
    if any(result.review_status != "verified" for result in response.results):
        raise RuntimeError("Live retrieval returned an unverified citation")
    if any(result.production_approved for result in response.results):
        raise RuntimeError(
            "Staging retrieval unexpectedly returned a production approval"
        )
    if negative_response.status != "NO_DATA" or negative_response.results:
        raise RuntimeError("Off-domain query did not fail closed with NO_DATA")

    print(
        json.dumps(
            {
                "ok": True,
                "query_case": "elder_general_information_allowed",
                "status": response.status,
                "result_count": len(response.results),
                "ranked_results": [
                    {
                        "rank": rank,
                        "chunk_id": result.chunk_id,
                        "score": round(result.score, 6),
                    }
                    for rank, result in enumerate(response.results, start=1)
                ],
                "review_status": "verified",
                "production_approved": False,
                "off_domain_status": negative_response.status,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(_main())
