"""Professional-only elder profile reads and versioned maintenance commands."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.schemas.elder_profile import (
    CreateCareProfileRequest,
    RetireCareProfileRequest,
    UpdateCareProfileRequest,
    UpdateElderProfileRequest,
)
from app.services.elder_profile_service import ElderProfileService

router = APIRouter(prefix="/api/v1/elders/{elder_id}", tags=["elder-profiles"])


def profile_service(
    response: Response,
    actor: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> ElderProfileService:
    response.headers["Cache-Control"] = "no-store"
    return ElderProfileService(session, actor)


@router.get("/profile")
async def get_elder_profile(
    elder_id: UUID, service: ElderProfileService = Depends(profile_service)
) -> dict:
    return success((await service.profile(elder_id)).model_dump(mode="json"))


@router.patch("/profile")
async def update_elder_profile(
    elder_id: UUID,
    request: UpdateElderProfileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    service: ElderProfileService = Depends(profile_service),
) -> dict:
    return success(
        await service.mutate(
            elder_id,
            request,
            operation="BASIC_UPDATED",
            key=idempotency_key,
            trace_id=get_correlation_id(),
        )
    )


@router.get("/care-profile")
async def list_care_profile(
    elder_id: UUID,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    include_retired: bool = Query(False),
    service: ElderProfileService = Depends(profile_service),
) -> dict:
    return success(
        (await service.care_list(elder_id, cursor, limit, include_retired)).model_dump(mode="json")
    )


@router.post("/care-profile", status_code=201)
async def create_care_profile(
    elder_id: UUID,
    request: CreateCareProfileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    service: ElderProfileService = Depends(profile_service),
) -> dict:
    return success(
        await service.mutate(
            elder_id,
            request,
            operation="CARE_ENTRY_CREATED",
            key=idempotency_key,
            trace_id=get_correlation_id(),
        )
    )


@router.patch("/care-profile/{entry_id}")
async def update_care_profile(
    elder_id: UUID,
    entry_id: UUID,
    request: UpdateCareProfileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    service: ElderProfileService = Depends(profile_service),
) -> dict:
    return success(
        await service.mutate(
            elder_id,
            request,
            operation="CARE_ENTRY_UPDATED",
            key=idempotency_key,
            trace_id=get_correlation_id(),
            entry_id=entry_id,
        )
    )


@router.post("/care-profile/{entry_id}/retire")
async def retire_care_profile(
    elder_id: UUID,
    entry_id: UUID,
    request: RetireCareProfileRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
    service: ElderProfileService = Depends(profile_service),
) -> dict:
    return success(
        await service.mutate(
            elder_id,
            request,
            operation="CARE_ENTRY_RETIRED",
            key=idempotency_key,
            trace_id=get_correlation_id(),
            entry_id=entry_id,
        )
    )


@router.get("/profile-history")
async def list_profile_history(
    elder_id: UUID,
    cursor: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    service: ElderProfileService = Depends(profile_service),
) -> dict:
    return success((await service.history(elder_id, cursor, limit)).model_dump(mode="json"))
