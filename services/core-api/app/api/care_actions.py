"""Professional Care Action endpoints."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.core.cursor import decode_cursor, encode_cursor
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.middleware.actor_guard import require_active_actor
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.care_action import (
    CareActionListResponse,
    CareActionResponse,
    CareActionStatus,
    CreateCareActionRequest,
    UpdateCareActionRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.care_action_service import CareActionService

router = APIRouter(prefix="/api/v1", tags=["care-actions"])


def _response(action) -> CareActionResponse:
    return CareActionResponse(
        care_action_id=action.id,
        elder_id=action.elder_id,
        action_type=action.action_type,
        title=action.title,
        description=action.description,
        trigger_reason=action.trigger_reason,
        related_event_ids=action.related_event_ids,
        assignee_actor_id=action.assignee_actor_id,
        due_at=action.due_at,
        priority=action.priority,
        status=action.status,
        resolution=action.resolution,
        created_by_actor_id=action.created_by_actor_id,
        version=action.version,
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


@router.get("/elders/{elder_id}/care-actions")
async def list_care_actions(
    elder_id: UUID = Path(...),
    action_status: list[CareActionStatus] | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_action:read")
    service = CareActionService(session, actor_context.tenant_id)
    service.require_professional(actor_context)
    actions = await service.list_for_elder(
        elder_id=elder_id,
        statuses=cast(list[str] | None, action_status),
        limit=limit,
        cursor=decode_cursor(cursor) if cursor else None,
    )
    has_more = len(actions) > limit
    page = actions[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more and page else None
    return success(
        CareActionListResponse(
            items=[_response(action) for action in page],
            next_cursor=next_cursor,
            has_more=has_more,
        ).model_dump(mode="json")
    )


@router.post(
    "/elders/{elder_id}/care-actions",
    status_code=status.HTTP_201_CREATED,
)
async def create_care_action(
    request: CreateCareActionRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_action:create")
    service = CareActionService(session, actor_context.tenant_id)
    service.require_professional(actor_context)
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_care_action",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    if replay.replayed and replay.response_body is not None:
        return success(replay.response_body)
    if replay.replayed:
        action = (
            await service.get(elder_id, replay.resource_id)
            if replay.resource_id is not None
            else None
        )
        if action is None:
            raise NotFoundError("Resource not found")
    else:
        action = await service.create(
            elder_id=elder_id,
            actor_context=actor_context,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        body = _response(action).model_dump(mode="json")
        await idem.complete(
            key=idempotency_key,
            resource_type="care_action",
            resource_id=action.id,
            response_status=status.HTTP_201_CREATED,
            response_body=body,
        )
    return success(_response(action).model_dump(mode="json"))


@router.patch("/elders/{elder_id}/care-actions/{care_action_id}")
async def update_care_action(
    request: UpdateCareActionRequest,
    elder_id: UUID = Path(...),
    care_action_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "care_action:update")
    service = CareActionService(session, actor_context.tenant_id)
    service.require_professional(actor_context)
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="update_care_action",
        payload={
            "elder_id": elder_id,
            "care_action_id": care_action_id,
            **request.model_dump(mode="json"),
        },
    )
    if replay.replayed and replay.response_body is not None:
        return success(replay.response_body)
    action = await service.get(elder_id, care_action_id)
    if action is None:
        raise NotFoundError("Resource not found")
    if not replay.replayed:
        action = await service.transition(
            action=action,
            actor_context=actor_context,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        body = _response(action).model_dump(mode="json")
        await idem.complete(
            key=idempotency_key,
            resource_type="care_action",
            resource_id=action.id,
            response_status=200,
            response_body=body,
        )
    return success(_response(action).model_dump(mode="json"))
