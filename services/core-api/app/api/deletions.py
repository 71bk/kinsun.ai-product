"""Read-only deletion workflow status endpoint."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import success
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.schemas.deletion import DeletionJobItemResponse, DeletionRequestResponse
from app.services.authorization_service import authorize_elder
from app.services.deletion_service import DeletionService

router = APIRouter(prefix="/api/v1", tags=["deletions"])


@router.get("/elders/{elder_id}/deletion-requests/{deletion_request_id}")
async def get_deletion_request(
    elder_id: UUID = Path(...),
    deletion_request_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "deletion:read")
    service = DeletionService(session, actor_context.tenant_id)
    deletion_request = await service.get(
        elder_id=elder_id,
        deletion_request_id=deletion_request_id,
    )
    if deletion_request is None:
        raise NotFoundError("Resource not found")
    items = await service.list_items(
        elder_id=elder_id,
        deletion_request_id=deletion_request.id,
    )
    body = DeletionRequestResponse(
        deletion_request_id=deletion_request.id,
        elder_id=deletion_request.elder_id,
        consent_id=deletion_request.consent_id,
        scope=deletion_request.scope,
        status=deletion_request.status,
        reason_code=deletion_request.reason_code,
        requested_at=deletion_request.requested_at,
        effective_at=deletion_request.effective_at,
        completed_at=deletion_request.completed_at,
        items=[
            DeletionJobItemResponse(
                deletion_job_item_id=item.deletion_job_item_id,
                resource_type=item.resource_type,
                system_of_record=item.system_of_record,
                status=item.status,
                attempt_count=item.attempt_count,
                started_at=item.started_at,
                failure_code=item.failure_code,
                completed_at=item.completed_at,
            )
            for item in items
        ],
    )
    return success(body.model_dump(mode="json"))
