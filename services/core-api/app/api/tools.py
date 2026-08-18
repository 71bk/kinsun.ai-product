"""Internal Core Tool execution endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import success
from app.core.auth import ActorContext
from app.db.session import get_db_session
from app.middleware.actor_guard import require_system_service_actor
from app.schemas.tool import ToolRequest
from app.services.tool_service import ToolExecutionService

router = APIRouter(prefix="/api/v1/internal", tags=["agent-tools"])


@router.post("/tools/execute")
async def execute_tool(
    request: ToolRequest,
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await ToolExecutionService(session, actor_context).execute(request)
    return success(result.model_dump(mode="json"))
