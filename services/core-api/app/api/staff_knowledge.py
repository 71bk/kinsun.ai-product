"""Authenticated, stateless staff queries over public official knowledge only."""

from fastapi import APIRouter, Depends, Response

from app.adapters.agent_runtime import AgentRuntimeClient, get_agent_runtime_client
from app.api.responses import success
from app.core.auth import ActorContext
from app.core.config import AppEnv, get_settings
from app.core.correlation import get_correlation_id
from app.core.exceptions import AuthorizationDeniedError, ServiceUnavailableError
from app.middleware.actor_guard import require_active_actor
from app.schemas.public_knowledge import PublicKnowledgeQuestion
from app.services.public_knowledge_service import answer_public_question

router = APIRouter(prefix="/api/v1/staff", tags=["staff-knowledge"])


async def require_staff(actor: ActorContext = Depends(require_active_actor)) -> ActorContext:
    if actor.actor_role not in {"DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"}:
        raise AuthorizationDeniedError("Resource not found")
    return actor


@router.post("/knowledge/questions")
async def ask_staff_knowledge(
    question: PublicKnowledgeQuestion,
    response: Response,
    actor: ActorContext = Depends(require_staff),
    client: AgentRuntimeClient = Depends(get_agent_runtime_client),
) -> dict:
    settings = get_settings()
    if settings.app_env == AppEnv.PRODUCTION or not settings.knowledge_router_v2_enabled:
        raise ServiceUnavailableError("Public knowledge service is unavailable")
    response.headers["Cache-Control"] = "no-store"
    answer = await answer_public_question(
        question, client=client, correlation_id=get_correlation_id(), audience="care_professional"
    )
    return success(answer.model_dump(mode="json"))
