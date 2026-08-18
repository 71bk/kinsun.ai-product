"""Care-assignment creation, listing, and state commands."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import (
    require_active_actor,
    require_system_service_actor,
)
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.assignment import (
    AssignmentCommandRequest,
    AssignmentListResponse,
    AssignmentResponse,
    CreateAssignmentRequest,
)
from app.services.assignment_service import AssignmentService
from app.services.authorization_service import authorize_elder

router = APIRouter(prefix="/api/v1", tags=["care-assignments"])


def _response(assignment) -> AssignmentResponse:
    return AssignmentResponse(
        assignment_id=assignment.id,
        elder_id=assignment.elder_id,
        provider_tenant_id=assignment.tenant_id,
        care_unit_id=assignment.care_unit_id,
        home_care_worker_id=assignment.worker_id,
        scheduled_start=assignment.service_start,
        scheduled_end=assignment.service_end,
        status=assignment.status,
        allowed_data_scopes=assignment.service_scope,
        version=assignment.version,
        expires_at=assignment.service_end,
    )


@router.post(
    "/internal/home-care/assignments",
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    request: CreateAssignmentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(
        session,
        actor_context,
        request.elder_id,
        "assignment:create",
    )
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_assignment",
        payload=request.model_dump(mode="json"),
    )
    service = AssignmentService(session, actor_context.tenant_id)
    if replay.replayed:
        assignment = (
            await service.get(replay.resource_id) if replay.resource_id is not None else None
        )
        if assignment is None:
            raise NotFoundError("Resource not found")
    else:
        assignment = await service.create(
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="care_assignment",
            resource_id=assignment.id,
            response_status=status.HTTP_201_CREATED,
            response_body={"assignment_id": str(assignment.id), "status": assignment.status},
        )
    return success(_response(assignment).model_dump(mode="json"))


@router.get("/home-care/assignments")
async def list_assignments(
    service_date: date = Query(default_factory=lambda: datetime.now(UTC).date(), alias="date"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AssignmentService(session, actor_context.tenant_id)
    assignments = await service.list_for_worker(
        worker_id=actor_context.actor_id,
        service_date=service_date,
    )
    return success(
        AssignmentListResponse(
            items=[_response(assignment) for assignment in assignments]
        ).model_dump(mode="json")
    )


@router.get("/home-care/assignments/{assignment_id}")
async def get_assignment(
    assignment_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = AssignmentService(session, actor_context.tenant_id)
    assignment = await service.get(assignment_id)
    if assignment is None:
        raise NotFoundError("Resource not found")
    await authorize_elder(session, actor_context, assignment.elder_id, "assignment:read")
    return success(_response(assignment).model_dump(mode="json"))


async def _assignment_command(
    *,
    assignment_id: UUID,
    target: str,
    request: AssignmentCommandRequest,
    idempotency_key: str,
    actor_context: ActorContext,
    session: AsyncSession,
) -> dict:
    service = AssignmentService(session, actor_context.tenant_id)
    assignment = await service.get(assignment_id)
    if assignment is None:
        raise NotFoundError("Resource not found")
    await authorize_elder(
        session,
        actor_context,
        assignment.elder_id,
        f"assignment:{target.lower()}",
    )
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation=f"assignment_{target.lower()}",
        payload={"assignment_id": assignment_id, **request.model_dump(mode="json")},
    )
    if not replay.replayed:
        assignment = await service.transition(
            assignment=assignment,
            target=target,
            actor_id=actor_context.actor_id,
            expected_version=request.expected_version,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="care_assignment",
            resource_id=assignment.id,
            response_status=200,
            response_body={"assignment_id": str(assignment.id), "status": assignment.status},
        )
    return success(_response(assignment).model_dump(mode="json"))


@router.post("/internal/home-care/assignments/{assignment_id}/confirm")
async def confirm_assignment(
    request: AssignmentCommandRequest,
    assignment_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _assignment_command(
        assignment_id=assignment_id,
        target="CONFIRMED",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/home-care/assignments/{assignment_id}/start")
async def start_assignment(
    request: AssignmentCommandRequest,
    assignment_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _assignment_command(
        assignment_id=assignment_id,
        target="IN_PROGRESS",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/home-care/assignments/{assignment_id}/complete")
async def complete_assignment(
    request: AssignmentCommandRequest,
    assignment_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _assignment_command(
        assignment_id=assignment_id,
        target="COMPLETED",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )
