"""Family-report draft, publication, withdrawal, and family-read endpoints."""

from __future__ import annotations

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
from app.schemas.report import (
    CreateFamilyReportDraftRequest,
    FamilyReportListResponse,
    FamilyReportResponse,
    PublishFamilyReportRequest,
    ReportType,
    WithdrawFamilyReportRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1", tags=["family-reports"])


async def _response(service: ReportService, report) -> FamilyReportResponse:
    version = await service.get_version(report)
    relationship_ids = [UUID(item) for item in report.recipient_scope.get("relationship_ids", [])]
    return FamilyReportResponse(
        report_id=report.id,
        elder_id=report.elder_id,
        recipient_scope_ids=relationship_ids,
        report_type=report.report_type,
        period_start=report.period_start,
        period_end=report.period_end,
        status=report.status,
        items=version.content.get("items", []),
        data_gap_notice=version.content.get("data_gap_notice"),
        sensitive_review_required=version.content.get(
            "sensitive_review_required",
            True,
        ),
        version=report.current_version,
        published_at=report.published_at,
        withdrawn_at=report.withdrawn_at,
        updated_at=report.updated_at,
    )


@router.post(
    "/internal/elders/{elder_id}/family-report-drafts",
    status_code=status.HTTP_201_CREATED,
)
async def create_family_report_draft(
    request: CreateFamilyReportDraftRequest,
    elder_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "family_report:draft:create")
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="create_family_report_draft",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = ReportService(session, actor_context.tenant_id)
    if replay.replayed:
        report = await service.get(replay.resource_id) if replay.resource_id is not None else None
        if report is None:
            raise NotFoundError("Resource not found")
    else:
        report = await service.create_draft(
            elder_id=elder_id,
            actor_id=actor_context.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
        await idem.complete(
            key=idempotency_key,
            resource_type="family_report",
            resource_id=report.id,
            response_status=status.HTTP_201_CREATED,
            response_body={"report_id": str(report.id), "status": report.status},
        )
    return success((await _response(service, report)).model_dump(mode="json"))


async def _report_command(
    *,
    report_id: UUID,
    operation: str,
    request: PublishFamilyReportRequest | WithdrawFamilyReportRequest,
    idempotency_key: str,
    actor_context: ActorContext,
    session: AsyncSession,
) -> dict:
    service = ReportService(session, actor_context.tenant_id)
    report = await service.get(report_id)
    if report is None:
        raise NotFoundError("Resource not found")
    await authorize_elder(
        session,
        actor_context,
        report.elder_id,
        f"family_report:{operation}",
    )
    idem = IdempotencyRepository(session, actor_context.tenant_id, actor_context.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation=f"family_report_{operation}",
        payload={"report_id": report_id, **request.model_dump(mode="json")},
    )
    if not replay.replayed:
        if operation == "publish":
            report = await service.publish(
                report=report,
                actor_id=actor_context.actor_id,
                expected_version=request.expected_version,
                trace_id=get_correlation_id(),
                idempotency_key=idempotency_key,
            )
        else:
            report = await service.withdraw(
                report=report,
                actor_id=actor_context.actor_id,
                expected_version=request.expected_version,
                reason_code=request.reason_code,
                trace_id=get_correlation_id(),
                idempotency_key=idempotency_key,
            )
        await idem.complete(
            key=idempotency_key,
            resource_type="family_report",
            resource_id=report.id,
            response_status=200,
            response_body={"report_id": str(report.id), "status": report.status},
        )
    return success((await _response(service, report)).model_dump(mode="json"))


@router.post("/internal/family-reports/{report_id}/publish")
async def publish_family_report(
    request: PublishFamilyReportRequest,
    report_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _report_command(
        report_id=report_id,
        operation="publish",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.post("/internal/family-reports/{report_id}/withdraw")
async def withdraw_family_report(
    request: WithdrawFamilyReportRequest,
    report_id: UUID = Path(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor_context: ActorContext = Depends(require_system_service_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await _report_command(
        report_id=report_id,
        operation="withdraw",
        request=request,
        idempotency_key=idempotency_key,
        actor_context=actor_context,
        session=session,
    )


@router.get("/family/elders/{elder_id}/reports")
async def list_family_reports(
    elder_id: UUID = Path(...),
    report_type: ReportType | None = Query(default=None, alias="type"),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor_context, elder_id, "family_report:read")
    service = ReportService(session, actor_context.tenant_id)
    reports = await service.list_for_family(
        elder_id=elder_id,
        actor_id=actor_context.actor_id,
        report_type=report_type.value if report_type else None,
    )
    items = [await _response(service, report) for report in reports]
    return success(FamilyReportListResponse(items=items).model_dump(mode="json"))


@router.get("/family/reports/{report_id}")
async def get_family_report(
    report_id: UUID = Path(...),
    actor_context: ActorContext = Depends(require_active_actor),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    service = ReportService(session, actor_context.tenant_id)
    report = await service.get_for_family(
        report_id=report_id,
        actor_id=actor_context.actor_id,
    )
    await authorize_elder(
        session,
        actor_context,
        report.elder_id,
        "family_report:read",
    )
    return success((await _response(service, report)).model_dump(mode="json"))
