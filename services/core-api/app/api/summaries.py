"""Source-backed daily-summary endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal
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
from app.schemas.summary import (
    CreateSummaryDraftRequest,
    GenerateSummaryRequest,
    RebuildSummaryRequest,
    ReviewSummaryRequest,
    SummaryListResponse,
    SummaryResponse,
    SummaryReviewResponse,
)
from app.services.authorization_service import authorize_elder
from app.services.summary_service import SummaryService

router = APIRouter(prefix="/api/v1", tags=["summaries"])

SummaryReadStatus = Literal[
    "DRAFT",
    "READY",
    "NEEDS_REVIEW",
    "PUBLISHED",
    "STALE",
    "WITHDRAWN",
]
ALLOWED_SUMMARY_STATUSES = frozenset(
    {
        "DRAFT",
        "READY",
        "NEEDS_REVIEW",
        "PUBLISHED",
        "STALE",
        "WITHDRAWN",
    }
)
FORMAL_SUMMARY_STATUSES = ("READY", "PUBLISHED")


async def _response(service: SummaryService, summary) -> SummaryResponse:
    version = await service.get_version(summary)
    return SummaryResponse(
        summary_id=summary.id,
        elder_id=summary.elder_id,
        summary_date=summary.summary_date,
        summary_type=summary.summary_type,
        status=summary.status,
        items=version.content.get("items", []),
        missing_fields=version.content.get("missing_fields", []),
        conflict_flags=version.content.get("conflict_flags", []),
        version=summary.current_version,
        generated_at=summary.generated_at,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


@router.post(
    "/internal/elders/{elder_id}/summary-drafts",
    status_code=status.HTTP_201_CREATED,
)
async def create_summary_draft(
    request: CreateSummaryDraftRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "summary:draft:create")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_summary_draft",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = SummaryService(session, actor_context.tenant_id)
    if replay.replayed:
        summary = (
            await service.get(elder_id, replay.resource_id)
            if replay.resource_id is not None
            else None
        )
        if summary is None:
            raise NotFoundError("Resource not found")
    else:
        summary = await service.create_draft(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="daily_summary",
            resource_id=summary.id,
            response_status=status.HTTP_201_CREATED,
            response_body={"summary_id": str(summary.id), "version": summary.current_version},
        )
    return success((await _response(service, summary)).model_dump(mode="json"))


@router.post(
    "/elders/{elder_id}/summaries/generate",
    status_code=status.HTTP_201_CREATED,
)
async def generate_summary(
    request: GenerateSummaryRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Human-triggered deterministic draft; it never publishes a family report."""

    await authorize_elder(session, actor_context, elder_id, "summary:review")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="generate_daily_summary",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = SummaryService(session, actor_context.tenant_id)
    if replay.replayed:
        summary = (
            await service.get(elder_id, replay.resource_id)
            if replay.resource_id is not None
            else None
        )
        if summary is None:
            raise NotFoundError("Resource not found")
    else:
        summary = await service.generate_from_verified_events(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            summary_date=request.summary_date,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="daily_summary",
            resource_id=summary.id,
            response_status=status.HTTP_201_CREATED,
            response_body={"summary_id": str(summary.id), "version": summary.current_version},
        )
    return success((await _response(service, summary)).model_dump(mode="json"))


@router.get("/elders/{elder_id}/summaries")
async def list_summaries(
    elder_id: UUID = Path(...),
    summary_date: date | None = Query(default=None, alias="date"),
    summary_status: list[SummaryReadStatus] | None = Query(
        default=None,
        alias="status",
        description=(
            "Defaults to formal READY and PUBLISHED summaries. "
            "Any explicit non-formal status additionally requires summary:review."
        ),
    ),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """List formal summaries by default; expose review states only to reviewers."""
    await authorize_elder(session, actor_context, elder_id, "summary:read")
    requested_statuses = summary_status or list(FORMAL_SUMMARY_STATUSES)
    if not set(requested_statuses).issubset(ALLOWED_SUMMARY_STATUSES):
        from app.core.exceptions import ValidationError

        raise ValidationError(
            details=[{"field": "status", "reason": "status contains an unsupported value"}]
        )
    if set(requested_statuses).difference(FORMAL_SUMMARY_STATUSES):
        await authorize_elder(session, actor_context, elder_id, "summary:review")
    service = SummaryService(session, actor_context.tenant_id)
    summaries = await service.list_for_date(
        elder_id=elder_id,
        summary_date=summary_date,
        statuses=requested_statuses,
    )
    items = [await _response(service, summary) for summary in summaries]
    return success(SummaryListResponse(items=items).model_dump(mode="json"))


@router.get("/elders/{elder_id}/summaries/{summary_id}")
async def get_summary(
    elder_id: UUID = Path(...),
    summary_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """Return a formal summary, or a non-formal summary only to a reviewer."""
    await authorize_elder(session, actor_context, elder_id, "summary:read")
    service = SummaryService(session, actor_context.tenant_id)
    summary = await service.get(
        elder_id,
        summary_id,
        statuses=list(FORMAL_SUMMARY_STATUSES),
    )
    if summary is None:
        await authorize_elder(session, actor_context, elder_id, "summary:review")
        summary = await service.get(
            elder_id,
            summary_id,
            statuses=list(ALLOWED_SUMMARY_STATUSES),
        )
    if summary is None:
        raise NotFoundError("Resource not found")
    return success((await _response(service, summary)).model_dump(mode="json"))


@router.post("/elders/{elder_id}/summaries/{summary_id}/review")
async def review_summary(
    request: ReviewSummaryRequest,
    elder_id: UUID = Path(...),
    summary_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "summary:review")
    service = SummaryService(session, actor_context.tenant_id)
    summary = await service.get(elder_id, summary_id)
    if summary is None:
        raise NotFoundError("Resource not found")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="review_summary",
        payload={
            "elder_id": elder_id,
            "summary_id": summary_id,
            **request.model_dump(mode="json"),
        },
    )
    if replay.replayed:
        review = await service.get_latest_review(summary.id)
        if review is None:
            raise NotFoundError("Resource not found")
    else:
        review = await service.review(
            summary=summary,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="daily_summary",
            resource_id=summary.id,
            response_status=200,
            response_body={
                "summary_id": str(summary.id),
                "status": summary.status,
                "review_record_id": str(review.review_id),
            },
        )
    body = (await _response(service, summary)).model_dump()
    return success(
        SummaryReviewResponse(
            **body,
            review_record_id=review.review_id,
        ).model_dump(mode="json")
    )


@router.post("/elders/{elder_id}/summaries/{summary_id}/rebuild")
async def rebuild_summary(
    request: RebuildSummaryRequest,
    elder_id: UUID = Path(...),
    summary_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "summary:rebuild")
    service = SummaryService(session, actor_context.tenant_id)
    summary = await service.get(elder_id, summary_id)
    if summary is None:
        raise NotFoundError("Resource not found")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="rebuild_summary",
        payload={
            "elder_id": elder_id,
            "summary_id": summary_id,
            **request.model_dump(mode="json"),
        },
    )
    if not replay.replayed:
        summary = await service.request_rebuild(
            summary=summary,
            actor_id=actor_context.actor_id,
            expected_version=request.expected_version,
            reason_code=request.reason_code,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="daily_summary",
            resource_id=summary.id,
            response_status=200,
            response_body={"summary_id": str(summary.id), "status": summary.status},
        )
    return success((await _response(service, summary)).model_dump(mode="json"))
