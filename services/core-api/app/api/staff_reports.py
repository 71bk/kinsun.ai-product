"""Staff-only report workspace. Internal system-service routes remain separate."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.reports import _response
from app.api.responses import get_correlation_id, success
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.db.session import get_db_session
from app.domain.consent import ConsentPurpose
from app.middleware.actor_guard import require_active_actor
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.report import (
    CreateReportFromSummaryRequest,
    PublishFamilyReportRequest,
    StaffReportWorkspaceResponse,
    WithdrawFamilyReportRequest,
)
from app.services.authorization_service import authorize_elder
from app.services.consent_service import ConsentService
from app.services.staff_report_service import StaffReportService

router = APIRouter(prefix="/api/v1/elders/{elder_id}", tags=["staff-family-reports"])


async def require_report_staff(actor: ActorContext = Depends(require_active_actor)) -> ActorContext:
    if actor.actor_role not in {"DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"}:
        raise NotFoundError("Resource not found")
    return actor


@router.get("/family-report-workspace")
async def report_workspace(
    elder_id: UUID,
    actor: ActorContext = Depends(require_report_staff),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor, elder_id, "family_report:draft:create")
    service = StaffReportService(session, actor.tenant_id)
    recipients = await service.recipients(elder_id)
    reports = await service._reports.list_for_staff(elder_id)
    return success(
        StaffReportWorkspaceResponse(
            recipients=recipients,
            reports=[await _response(service, report) for report in reports],
        ).model_dump(mode="json")
    )


@router.post("/family-reports/from-summary", status_code=201)
async def create_report_from_summary(
    elder_id: UUID,
    request: CreateReportFromSummaryRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_report_staff),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    await authorize_elder(session, actor, elder_id, "family_report:draft:create")
    await authorize_elder(session, actor, elder_id, "summary:read")
    for purpose in (ConsentPurpose.FAMILY_SHARING, ConsentPurpose.CARE_EVENT_EXTRACTION):
        await ConsentService(session, actor.tenant_id).require_active(
            elder_id=elder_id, purpose=purpose
        )
    idem = IdempotencyRepository(session, actor.tenant_id, actor.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation="staff_report_from_summary",
        payload={"elder_id": elder_id, **request.model_dump(mode="json")},
    )
    service = StaffReportService(session, actor.tenant_id)
    if replay.replayed:
        report = (
            await service.get_for_elder(elder_id, replay.resource_id)
            if replay.resource_id
            else None
        )
        if report is None:
            raise NotFoundError("Resource not found")
    else:
        report = await service.create_from_summary(
            elder_id=elder_id,
            actor_id=actor.actor_id,
            request=request,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
    body = (await _response(service, report)).model_dump(mode="json")
    if not replay.replayed:
        await idem.complete(
            key=idempotency_key,
            resource_type="family_report",
            resource_id=report.id,
            response_status=201,
            response_body=body,
        )
    return success(body)


async def staff_report_command(
    *,
    elder_id: UUID,
    report_id: UUID,
    operation: str,
    request: PublishFamilyReportRequest | WithdrawFamilyReportRequest,
    idempotency_key: str,
    actor: ActorContext,
    session: AsyncSession,
) -> dict:
    await authorize_elder(session, actor, elder_id, f"family_report:{operation}")
    service = StaffReportService(session, actor.tenant_id)
    # Lock before idempotency so concurrent publish/withdraw commands see current state.
    report = await service._reports.get_for_update(elder_id, report_id)
    if report is None:
        raise NotFoundError("Resource not found")
    if operation == "publish":
        await ConsentService(session, actor.tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.FAMILY_SHARING,
        )
    idem = IdempotencyRepository(session, actor.tenant_id, actor.actor_id)
    replay = await idem.begin(
        key=idempotency_key,
        operation=f"staff_report_{operation}",
        payload={"elder_id": elder_id, "report_id": report_id, **request.model_dump(mode="json")},
    )
    if not replay.replayed:
        command = service.publish if operation == "publish" else service.withdraw
        report = await command(
            report=report,
            actor_id=actor.actor_id,
            expected_version=request.expected_version,
            reason_code=request.reason_code,
            trace_id=get_correlation_id(),
            idempotency_key=idempotency_key,
        )
    body = (await _response(service, report)).model_dump(mode="json")
    if not replay.replayed:
        await idem.complete(
            key=idempotency_key,
            resource_type="family_report",
            resource_id=report.id,
            response_status=200,
            response_body=body,
        )
    return success(body)


@router.post("/family-reports/{report_id}/publish")
async def publish_staff_report(
    elder_id: UUID,
    report_id: UUID,
    request: PublishFamilyReportRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_report_staff),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await staff_report_command(
        elder_id=elder_id,
        report_id=report_id,
        operation="publish",
        request=request,
        idempotency_key=idempotency_key,
        actor=actor,
        session=session,
    )


@router.post("/family-reports/{report_id}/withdraw")
async def withdraw_staff_report(
    elder_id: UUID,
    report_id: UUID,
    request: WithdrawFamilyReportRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    actor: ActorContext = Depends(require_report_staff),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    return await staff_report_command(
        elder_id=elder_id,
        report_id=report_id,
        operation="withdraw",
        request=request,
        idempotency_key=idempotency_key,
        actor=actor,
        session=session,
    )
