"""Professional review endpoints for AI Care Action candidates."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.care_action import (
    AdoptCareActionCandidateRequest,
    CareActionCandidateListResponse,
    CareActionCandidateResponse,
    CareActionCandidateStatus,
    CareActionSourceEventProvenance,
    DismissCareActionCandidateRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.care_action_candidate_service import CareActionCandidateService

router = APIRouter(prefix="/api/v1", tags=["care-action-candidates"])


def _response(candidate) -> CareActionCandidateResponse:
    return CareActionCandidateResponse(
        care_action_candidate_id=candidate.id,
        elder_id=candidate.elder_id,
        action_type=candidate.action_type,
        suggested_title=candidate.suggested_title,
        trigger_reason=candidate.trigger_reason,
        source_event_provenance=[
            CareActionSourceEventProvenance(
                event_id=source.event_id,
                event_version_id=source.event_version_id,
                event_version=source.event_version,
                event_type=source.event_type,
                event_time=source.event_time,
                source_status=source.source_status,
                snapshot_sha256=source.snapshot_sha256,
                snapshot_schema_version=source.snapshot_schema_version,
            )
            for source in candidate.source_event_provenance
        ],
        suggested_due_at=candidate.suggested_due_at,
        priority=candidate.priority,
        status=candidate.status,
        disposition_reason_code=candidate.disposition_reason_code,
        disposition_notes=candidate.disposition_notes,
        decided_by_actor_id=candidate.decided_by_actor_id,
        decided_at=candidate.decided_at,
        adopted_care_action_id=candidate.adopted_care_action_id,
        extractor_version=candidate.extractor_version,
        version=candidate.version,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


@router.get("/elders/{elder_id}/care-action-candidates")
async def list_care_action_candidates(
    elder_id: UUID = Path(...),
    candidate_status: list[CareActionCandidateStatus] | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_action:read")
    service = CareActionCandidateService(session, actor_context.tenant_id)
    service.require_professional(actor_context)
    candidates = await service.list_for_elder(
        elder_id=elder_id,
        statuses=cast(list[str], candidate_status or ["PENDING_REVIEW"]),
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    has_more = len(candidates) > limit
    page = candidates[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    return success(
        CareActionCandidateListResponse(
            items=[_response(candidate) for candidate in page],
            next_cursor=next_cursor,
            has_more=has_more,
        ).model_dump(mode="json")
    )


@router.post("/elders/{elder_id}/care-action-candidates/{candidate_id}/adopt")
async def adopt_care_action_candidate(
    request: AdoptCareActionCandidateRequest,
    elder_id: UUID = Path(...),
    candidate_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_action:create")
    service = CareActionCandidateService(session, actor_context.tenant_id)
    service.require_professional(actor_context)
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="adopt_care_action_candidate",
        payload={
            "elder_id": elder_id,
            "candidate_id": candidate_id,
            **request.model_dump(mode="json"),
        },
    )
    if replay.replayed and replay.response_body is not None:
        return success(replay.response_body)
    candidate = await service.get(elder_id, candidate_id, for_update=True)
    if candidate is None:
        raise NotFoundError("Resource not found")
    if not replay.replayed:
        candidate, _ = await service.adopt(
            candidate=candidate,
            actor_context=actor_context,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        body = _response(candidate).model_dump(mode="json")
        await idem.complete(
            key=idempotency_key,
            resource_type="care_action_candidate",
            resource_id=candidate.id,
            response_status=200,
            response_body=body,
        )
    return success(_response(candidate).model_dump(mode="json"))


@router.post("/elders/{elder_id}/care-action-candidates/{candidate_id}/dismiss")
async def dismiss_care_action_candidate(
    request: DismissCareActionCandidateRequest,
    elder_id: UUID = Path(...),
    candidate_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_action:update")
    service = CareActionCandidateService(session, actor_context.tenant_id)
    service.require_professional(actor_context)
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="dismiss_care_action_candidate",
        payload={
            "elder_id": elder_id,
            "candidate_id": candidate_id,
            **request.model_dump(mode="json"),
        },
    )
    if replay.replayed and replay.response_body is not None:
        return success(replay.response_body)
    candidate = await service.get(elder_id, candidate_id, for_update=True)
    if candidate is None:
        raise NotFoundError("Resource not found")
    if not replay.replayed:
        candidate = await service.dismiss(
            candidate=candidate,
            actor_context=actor_context,
            request=request,
        )
        body = _response(candidate).model_dump(mode="json")
        await idem.complete(
            key=idempotency_key,
            resource_type="care_action_candidate",
            resource_id=candidate.id,
            response_status=200,
            response_body=body,
        )
    return success(_response(candidate).model_dump(mode="json"))
