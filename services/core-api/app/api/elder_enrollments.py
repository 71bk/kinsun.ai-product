"""Independent enrollment management surface; never returns care data."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.schemas.elder_enrollment import EnrollmentCommand
from app.services.elder_enrollment_service import ElderEnrollmentService

router = APIRouter(prefix="/api/v1/elder-enrollments", tags=["elder-enrollments"])


def enrollment_service(
    response: Response,
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> ElderEnrollmentService:
    response.headers["Cache-Control"] = "no-store"
    return ElderEnrollmentService(session, actor)


@router.get("")
async def list_enrollments(
    cursor: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    service: ElderEnrollmentService = Depends(enrollment_service),
) -> dict:
    return success((await service.list(cursor, limit)).model_dump(mode="json"))


@router.get("/{enrollment_id}")
async def get_enrollment(
    enrollment_id: UUID,
    service: ElderEnrollmentService = Depends(enrollment_service),
) -> dict:
    return success((await service.get(enrollment_id)).model_dump(mode="json"))


@router.get("/{enrollment_id}/history")
async def enrollment_history(
    enrollment_id: UUID,
    cursor: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    service: ElderEnrollmentService = Depends(enrollment_service),
) -> dict:
    return success((await service.history(enrollment_id, cursor, limit)).model_dump(mode="json"))


@router.post("/{enrollment_id}/{action}")
async def change_enrollment(
    enrollment_id: UUID,
    action: Literal["suspend", "resume", "end"],
    request: EnrollmentCommand,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=160),
    service: ElderEnrollmentService = Depends(enrollment_service),
) -> dict:
    return success(
        await service.command(enrollment_id, action, request, idempotency_key, get_correlation_id())
    )
