"""Authenticated, stateless family queries over public official knowledge only."""

from fastapi import APIRouter, Depends, Response

from app.adapters.agent_runtime import AgentRuntimeClient, get_agent_runtime_client
from app.api.responses import success
from app.core.auth import ActorContext
from app.core.config import AppEnv, get_settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import AuthorizationDeniedError, ServiceUnavailableError
from app.middleware.actor_guard import require_active_actor
from app.schemas.family_knowledge import FamilyKnowledgeQuestion
from app.services.family_knowledge_service import answer_public_question

router = APIRouter(prefix="/api/v1/family", tags=["family-knowledge"])


async def require_family(actor: ActorContext = Depends(require_active_actor)) -> ActorContext:
    if actor.actor_role != "FAMILY_MEMBER":
        raise AuthorizationDeniedError("Resource not found")
    return actor


@router.post("/knowledge/questions")
async def ask_family_knowledge(
    question: FamilyKnowledgeQuestion,
    response: Response,
    actor: ActorContext = Depends(require_family),
    client: AgentRuntimeClient = Depends(get_agent_runtime_client),
) -> dict:
    settings = get_settings()
    if settings.app_env == AppEnv.PRODUCTION or not settings.knowledge_router_v2_enabled:
        raise ServiceUnavailableError("Public knowledge service is unavailable")
    response.headers["Cache-Control"] = "no-store"
    answer = await answer_public_question(
        question, client=client, correlation_id=get_correlation_id()
    )
    return success(answer.model_dump(mode="json"))
