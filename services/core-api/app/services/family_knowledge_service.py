"""Keep the family audience fixed while sharing public query orchestration."""

from app.schemas.family_knowledge import FamilyKnowledgeAnswer, FamilyKnowledgeQuestion
from app.services.public_knowledge_service import PublicKnowledgeReader
from app.services.public_knowledge_service import answer_public_question as _answer


async def answer_public_question(
    question: FamilyKnowledgeQuestion, *, client: PublicKnowledgeReader, correlation_id: str
) -> FamilyKnowledgeAnswer:
    return await _answer(
        question, client=client, correlation_id=correlation_id, audience="family_caregiver"
    )
