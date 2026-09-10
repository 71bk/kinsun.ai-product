"""Explicitly authorized synthetic live smoke, without changing persistent config."""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/agent-runtime/src"))
os.environ["RAG_POSTGRES_RELEASE_ID"] = "rag-v2-v004-f3339ceae77c"
os.environ["RAG_SOURCE_FAMILY_POLICY_PATH"] = "data/rag-v3/governance/source-family-policy/runtime/candidates/v004/source-family-runtime-policy.json"
os.environ["RAG_SOURCE_FAMILY_POLICY_EXPECTED_SHA256"] = "a7d8dd163e54bb5cb11f1ea4004e3a6b75b9faff98290067e745125cc6ac5758"

from agent_runtime.app import build_configured_rag_retriever
from agent_runtime.orchestration.rag_integration import _retrieval_query
from agent_runtime.rag.models import RetrievalRequestV2


async def main():
    retriever = build_configured_rag_retriever()
    if retriever is None:
        print(json.dumps({"status": "INITIALIZATION_FAILED"}))
        return 1
    try:
        for index, (query, audience, purpose) in enumerate([
            ("長照法", "elder", "legal_reference"),
            ("長照法第二條", "elder", "legal_reference"),
            ("長照法第2條", "family_caregiver", "legal_reference"),
            ("長照法第二條", "care_professional", "legal_reference"),
            ("長照法第二條", "elder", "disallowed_purpose"),
        ]):
            response = await retriever.retrieve_v2(RetrievalRequestV2(
                schema_version="2.0.0", request_id=f"law-repair-smoke-{index}",
                query=_retrieval_query("legal", query), query_profile="legal", top_k=5,
                audience=audience, purpose=purpose,
            ))
            rows = [row.model_dump(mode="json") for row in response.results]
            print(json.dumps({"query": query, "audience": audience, "purpose": purpose,
                              "status": response.status, "count": len(rows),
                              "results": [{key: value for key, value in row.items() if key != "text"}
                                          for row in rows]}, ensure_ascii=False), flush=True)
    finally:
        await retriever.aclose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        raise SystemExit(1)
