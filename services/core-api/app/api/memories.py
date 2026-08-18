"""Memory candidate and confirmed-memory endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.middleware.auth import ActorContext
from app.policies.memory_retrieval import memory_content_digest
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.consent import ConsentPurpose
from app.schemas.memory import (
    ConfirmMemoryRequest,
    CreateMemoryCandidateRequest,
    MemoryDecisionRequest,
    MemoryDeletionResponse,
    MemoryListResponse,
    MemoryResponse,
    UpdateMemoryRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.consent_service import ConsentService
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/api/v1", tags=["memories"])


async def _response(service: MemoryService, memory) -> MemoryResponse:
    version = await service.get_version(memory)
    return MemoryResponse(
        memory_id=memory.id,
        elder_id=memory.elder_id,
        memory_type=memory.memory_type,
        content=version.content,
        status=memory.status,
        source_event_ids=version.source_event_ids,
        confirmed_by=memory.confirmed_by_actor_id,
        confirmed_at=memory.confirmed_at,
        version=memory.current_version,
        active_from=memory.activated_at,
        inactive_at=memory.deactivated_at,
        consent_version=memory.consent_version,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


async def _begin(
    *,
    session: AsyncSession,
    actor_context: ActorContext,
    key: str,
    operation: str,
    payload: dict,
):
    repository = IdempotencyRepository(
        session,
        actor_context.tenant_id,
        actor_context.actor_id,
    )
    result = await repository.begin(
        key=key,
        operation=operation,
        payload=payload,
    )
    return repository, result


@router.post(
    "/elders/{elder_id}/memory-candidates",
    status_code=status.HTTP_201_CREATED,
)
async def create_memory_candidate(
    request: CreateMemoryCandidateRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "memory:candidate:create")
    idem, replay = await _begin(
        session=session,
        actor_context=actor_context,
        key=idempotency_key,
        operation="create_memory_candidate",
        payload={
            "elder_id": elder_id,
            "memory_type": request.memory_type.value,
            "memory_kind": request.memory_kind.value,
            "content_digest": memory_content_digest(request.normalized_content),
            "confirmation_question_digest": memory_content_digest(request.confirmation_question),
            "source_event_ids": request.source_event_ids,
            "possible_conflict": request.possible_conflict,
            "conflict_with_memory_ids": request.conflict_with_memory_ids,
            "extractor_version": request.extractor_version,
            "extraction_confidence": request.extraction_confidence,
            "proposal_risk_hint": request.proposal_risk_hint.value,
        },
    )
    service = MemoryService(session, actor_context.tenant_id)
    if replay.replayed:
        memory = (
            await service.get(elder_id, replay.resource_id)
            if replay.resource_id is not None
            else None
        )
        if memory is None:
            raise NotFoundError("Resource not found")
    else:
        memory = await service.create_candidate(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        body = (await _response(service, memory)).model_dump(mode="json")
        await idem.complete(
            key=idempotency_key,
            resource_type="memory",
            resource_id=memory.id,
            response_status=status.HTTP_201_CREATED,
            response_body=body,
        )
    return success((await _response(service, memory)).model_dump(mode="json"))


async def _list_memories(
    *,
    elder_id: UUID,
    statuses: list[str],
    cursor: str | None,
    limit: int,
    actor_context: ActorContext,
    session: AsyncSession,
) -> dict:
    await ConsentService(session, actor_context.tenant_id).require_active(
        elder_id=elder_id,
        purpose=ConsentPurpose.LONG_TERM_MEMORY,
    )
    service = MemoryService(session, actor_context.tenant_id)
    memories = await service.list_for_elder(
        elder_id=elder_id,
        statuses=statuses,
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    has_more = len(memories) > limit
    page = memories[:limit]
    items = [await _response(service, memory) for memory in page]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    return success(
        MemoryListResponse(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        ).model_dump(mode="json")
    )


@router.get("/elders/{elder_id}/memory-candidates")
async def list_memory_candidates(
    elder_id: UUID = Path(...),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "memory:candidate:read")
    return await _list_memories(
        elder_id=elder_id,
        statuses=["CANDIDATE", "PENDING_CONFIRMATION", "DEFERRED"],
        cursor=cursor,
        limit=limit,
        actor_context=actor_context,
        session=session,
    )


@router.get("/elders/{elder_id}/memories")
async def list_memories(
    elder_id: UUID = Path(...),
    memory_status: str = Query(default="ACTIVE", alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "memory:read")
    if memory_status not in {"ACTIVE", "INACTIVE"}:
        raise ValidationError(
            details=[
                {
                    "field": "status",
                    "reason": "only ACTIVE or INACTIVE confirmed memories can be listed",
                }
            ]
        )
    return await _list_memories(
        elder_id=elder_id,
        statuses=[memory_status],
        cursor=cursor,
        limit=limit,
        actor_context=actor_context,
        session=session,
    )


async def _candidate_decision(
    *,
    elder_id: UUID,
    memory_id: UUID,
    operation: str,
    request: ConfirmMemoryRequest | MemoryDecisionRequest,
    idempotency_key: str,
    actor_context: ActorContext,
    session: AsyncSession,
) -> dict:
    await authorize_elder(session, actor_context, elder_id, f"memory:{operation}")
    service = MemoryService(session, actor_context.tenant_id)
    memory = await service.get(elder_id, memory_id)
    if memory is None:
        raise NotFoundError("Resource not found")
    idem, replay = await _begin(
        session=session,
        actor_context=actor_context,
        key=idempotency_key,
        operation=f"memory_{operation}",
        payload={
            "elder_id": elder_id,
            "memory_id": memory_id,
            **request.model_dump(mode="json"),
        },
    )
    if not replay.replayed:
        if operation == "confirm":
            memory = await service.confirm(
                memory=memory,
                actor_context=actor_context,
                request=request,
                trace_id=get_correlation_id(),
                idempotency_key=idempotency_key,
            )
        else:
            target = {"reject": "REJECTED", "defer": "DEFERRED"}[operation]
            memory = await service.set_candidate_state(
                memory=memory,
                target=target,
                actor_id=actor_context.actor_id,
                expected_version=request.expected_version,
                trace_id=get_correlation_id(),
                idempotency_key=idempotency_key,
            )
        await idem.complete(
            key=idempotency_key,
            resource_type="memory",
            resource_id=memory.id,
            response_status=200,
            response_body={
                "memory_id": str(memory.id),
                "status": memory.status,
            },
        )
    return success((await _response(service, memory)).model_dump(mode="json"))


@router.post("/elders/{elder_id}/memory-candidates/{memory_id}/confirm")
async def confirm_memory(
    request: ConfirmMemoryRequest,
    elder_id: UUID = Path(...),
    memory_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _candidate_decision(
        elder_id=elder_id,
        memory_id=memory_id,
        operation="confirm",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/elders/{elder_id}/memory-candidates/{memory_id}/reject")
async def reject_memory(
    request: MemoryDecisionRequest,
    elder_id: UUID = Path(...),
    memory_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _candidate_decision(
        elder_id=elder_id,
        memory_id=memory_id,
        operation="reject",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/elders/{elder_id}/memory-candidates/{memory_id}/defer")
async def defer_memory(
    request: MemoryDecisionRequest,
    elder_id: UUID = Path(...),
    memory_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _candidate_decision(
        elder_id=elder_id,
        memory_id=memory_id,
        operation="defer",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.patch("/elders/{elder_id}/memories/{memory_id}")
async def update_memory(
    request: UpdateMemoryRequest,
    elder_id: UUID = Path(...),
    memory_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "memory:update")
    service = MemoryService(session, actor_context.tenant_id)
    memory = await service.get(elder_id, memory_id)
    if memory is None:
        raise NotFoundError("Resource not found")
    idem, replay = await _begin(
        session=session,
        actor_context=actor_context,
        key=idempotency_key,
        operation="memory_update",
        payload={
            "elder_id": elder_id,
            "memory_id": memory_id,
            **request.model_dump(mode="json"),
        },
    )
    if not replay.replayed:
        memory = await service.update(
            memory=memory,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="memory",
            resource_id=memory.id,
            response_status=200,
            response_body={"memory_id": str(memory.id), "version": memory.current_version},
        )
    return success((await _response(service, memory)).model_dump(mode="json"))


@router.delete("/elders/{elder_id}/memories/{memory_id}")
async def delete_memory(
    request: MemoryDecisionRequest,
    elder_id: UUID = Path(...),
    memory_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "memory:delete")
    service = MemoryService(session, actor_context.tenant_id)
    memory = await service.get(elder_id, memory_id)
    if memory is None:
        raise NotFoundError("Resource not found")
    idem, replay = await _begin(
        session=session,
        actor_context=actor_context,
        key=idempotency_key,
        operation="memory_delete",
        payload={
            "elder_id": elder_id,
            "memory_id": memory_id,
            **request.model_dump(mode="json"),
        },
    )
    if not replay.replayed:
        memory = await service.delete(
            memory=memory,
            actor_id=actor_context.actor_id,
            expected_version=request.expected_version,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="memory",
            resource_id=memory.id,
            response_status=200,
            response_body={"memory_id": str(memory.id), "status": "DELETED"},
        )
    return success(
        MemoryDeletionResponse(memory_id=memory.id, status="DELETED").model_dump(mode="json")
    )
