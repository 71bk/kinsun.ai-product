"""Professional notes on the caller's live, in-progress assignment only."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.schemas.service_record import CreateServiceRecordRequest
from app.services.service_record_service import ServiceRecordService

router = APIRouter(prefix="/api/v1/home-care/assignments", tags=["service-records"])


@router.post("/{assignment_id}/service-record/complete", status_code=201)
async def create_service_record_and_complete(
    assignment_id: UUID,
    request: CreateServiceRecordRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Atomically submit a note and complete its visit; return a content-free receipt.

    Requires assignment:read, service_record:write and assignment:complete on
    this exact live IN_PROGRESS assignment. Completion ends access: subsequent
    requests, including retries of a successful command, return the same 404 as
    unavailable assignments. No post-service grace period is granted.
    """
    return success(
        await ServiceRecordService(session, actor).create_and_complete(
            assignment_id, request, idempotency_key, get_correlation_id()
        )
    )


@router.get("/{assignment_id}/service-record")
async def get_service_record(
    assignment_id: UUID,
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return success(await ServiceRecordService(session, actor).get(assignment_id))


@router.post("/{assignment_id}/service-record", status_code=201)
async def create_service_record(
    assignment_id: UUID,
    request: CreateServiceRecordRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160),
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return success(
        await ServiceRecordService(session, actor).create(
            assignment_id,
            request,
            idempotency_key,
            get_correlation_id(),
        )
    )
