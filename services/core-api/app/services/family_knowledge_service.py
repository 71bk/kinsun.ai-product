"""Stateless public-information routing with no elder record or memory access."""

from uuid import uuid4

from app.adapters.agent_runtime import AgentRuntimeClient
from app.schemas.family_knowledge import FamilyKnowledgeAnswer, FamilyKnowledgeQuestion
from app.services.knowledge_router import route_knowledge


async def answer_public_question(
    question: FamilyKnowledgeQuestion, *, client: AgentRuntimeClient, correlation_id: str
) -> FamilyKnowledgeAnswer:
    route = route_knowledge(question.question, enabled=True)
    if route.reason_code == "LOOKUP_DECLINED":
        return FamilyKnowledgeAnswer(
            status="NO_DATA",
            answer="No search was performed." if question.language == "en-US" else "已停止查詢。",
        )
    if route.reason_code == "PRIVATE_CONTEXT":
        return FamilyKnowledgeAnswer(
            status="NO_DATA",
            answer=(
                "This page only provides public care information "
                "and cannot access personal records."
                if question.language == "en-US"
                else "此處只提供公開長照資訊，無法查詢個人的照護紀錄。"
            ),
        )
    # This dedicated entry never switches to private memory/companion tools.
    purpose = "legal_reference" if route.purpose == "legal_reference" else "general_information"
    answer = await client.retrieve_public_knowledge(
        request_payload={
            "schema_version": "3.0.0",
            "request_id": f"knowledge-{uuid4()}",
            "query": question.question,
            "query_profile": "legal" if purpose == "legal_reference" else "natural_language",
            "top_k": 5,
            "audience": "family_caregiver",
            "purpose": purpose,
            "language": question.language,
        },
        correlation_id=correlation_id,
    )
    return answer
