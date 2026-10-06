"""Compatibility names for the existing family public-knowledge contract."""

from app.schemas.public_knowledge import PublicKnowledgeAnswer, PublicKnowledgeQuestion
from app.schemas.public_knowledge import (
    PublicKnowledgeSource as PublicKnowledgeSource,
)

FamilyKnowledgeAnswer = PublicKnowledgeAnswer
FamilyKnowledgeQuestion = PublicKnowledgeQuestion
