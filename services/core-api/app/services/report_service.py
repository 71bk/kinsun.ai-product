"""Family-report publication gate and family-scoped read service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.consent import ConsentPurpose
from app.domain.state_machine import require_report_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.care_event import CareEvent
from app.models.report import FamilyReport, ReportVersion
from app.models.summary import DailySummary
from app.repositories.report_repo import ReportRepository
from app.schemas.report import CreateFamilyReportDraftRequest
from app.services.consent_service import ConsentService

REPORT_SCOPE = {
    "DAILY": "REPORT_DAILY",
    "WEEKLY": "REPORT_WEEKLY",
    "MONTHLY": "REPORT_MONTHLY",
    "IMPORTANT_EVENT": "REPORT_IMPORTANT_EVENT",
}


class ReportService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._reports = ReportRepository(session, tenant_id)

    async def get(self, report_id: UUID) -> FamilyReport | None:
        return await self._reports.get(report_id)

    async def get_for_elder(self, elder_id: UUID, report_id: UUID) -> FamilyReport | None:
        return await self._reports.get_for_elder(elder_id, report_id)

    async def get_version(self, report: FamilyReport) -> ReportVersion:
        return await self._reports.get_current_version(report)

    async def create_draft(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateFamilyReportDraftRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyReport:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.FAMILY_SHARING,
        )
        relationship_ids = await self._validate_recipient_scope(
            elder_id=elder_id,
            report_type=request.report_type.value,
            relationship_ids=request.recipient_scope_ids,
            consent_id=consent.id,
        )
        await self._validate_sources(
            elder_id=elder_id,
            source_event_ids=request.source_event_ids,
            source_summary_ids=request.source_summary_ids,
        )

        report = FamilyReport(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            recipient_scope={"relationship_ids": [str(item) for item in relationship_ids]},
            report_type=request.report_type.value,
            period_start=request.period_start,
            period_end=request.period_end,
            status="NEEDS_REVIEW",
            current_version=1,
            created_by_actor_id=actor_id,
        )
        self._reports.add_report(report)
        await self._session.flush()
        self._reports.add_version(
            ReportVersion(
                report_id=report.id,
                version=1,
                content={
                    "items": [item.model_dump(mode="json") for item in request.items],
                    "data_gap_notice": request.data_gap_notice,
                    "sensitive_review_required": request.sensitive_review_required,
                },
                source_summary_ids=request.source_summary_ids,
                source_event_ids=request.source_event_ids,
                share_scope_snapshot=report.recipient_scope,
                created_by_actor_id=actor_id,
            )
        )
        await self._session.flush()
        await self._write_event(
            event_type="family.report.generated.v1",
            report=report,
            actor_id=actor_id,
            consent_version=consent.version,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return report

    async def publish(
        self,
        *,
        report: FamilyReport,
        actor_id: UUID,
        expected_version: int,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyReport:
        if report.current_version != expected_version:
            raise ConflictError("Family report version conflict")
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=report.elder_id,
            purpose=ConsentPurpose.FAMILY_SHARING,
        )
        version = await self._reports.get_current_version(report)
        try:
            relationship_ids = [
                UUID(item) for item in report.recipient_scope.get("relationship_ids", [])
            ]
        except (TypeError, ValueError) as exc:
            raise ConflictError("Family report recipient scope is invalid") from exc
        if not relationship_ids:
            raise ConflictError("Family report has no active recipient scope")
        await self._validate_recipient_scope(
            elder_id=report.elder_id,
            report_type=report.report_type,
            relationship_ids=relationship_ids,
            consent_id=consent.id,
        )
        await self._validate_sources(
            elder_id=report.elder_id,
            source_event_ids=version.source_event_ids,
            source_summary_ids=version.source_summary_ids,
        )
        require_report_transition(report.status, "PUBLISHED")
        report.status = "PUBLISHED"
        report.published_at = datetime.now(UTC)
        await self._session.flush()
        await self._write_event(
            event_type="family.report.published.v1",
            report=report,
            actor_id=actor_id,
            consent_version=consent.version,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return report

    async def withdraw(
        self,
        *,
        report: FamilyReport,
        actor_id: UUID,
        expected_version: int,
        reason_code: str,
        trace_id: str,
        idempotency_key: str,
    ) -> FamilyReport:
        if report.current_version != expected_version:
            raise ConflictError("Family report version conflict")
        require_report_transition(report.status, "WITHDRAWN")
        report.status = "WITHDRAWN"
        report.withdrawn_at = datetime.now(UTC)
        await self._session.flush()
        await self._write_event(
            event_type="family.report.withdrawn.v1",
            report=report,
            actor_id=actor_id,
            consent_version=None,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            extra_payload={"reason_code": reason_code},
        )
        return report

    async def list_for_family(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        report_type: str | None,
    ) -> list[FamilyReport]:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.FAMILY_SHARING,
        )
        reports = await self._reports.list_published(
            elder_id=elder_id,
            report_type=report_type,
        )
        allowed: list[FamilyReport] = []
        now = datetime.now(UTC)
        for report in reports:
            for relationship_id in report.recipient_scope.get("relationship_ids", []):
                try:
                    parsed_relationship_id = UUID(relationship_id)
                except (TypeError, ValueError):
                    continue
                relationship = await self._reports.get_family_relationship(
                    relationship_id=parsed_relationship_id,
                    elder_id=elder_id,
                    actor_id=actor_id,
                    current_time=now,
                )
                if relationship is not None and relationship.consent_id == consent.id:
                    allowed.append(report)
                    break
        return allowed

    async def get_for_family(
        self,
        *,
        report_id: UUID,
        actor_id: UUID,
    ) -> FamilyReport:
        report = await self._reports.get(report_id)
        if report is None or report.status != "PUBLISHED":
            raise NotFoundError("Resource not found")
        allowed = await self.list_for_family(
            elder_id=report.elder_id,
            actor_id=actor_id,
            report_type=report.report_type,
        )
        if report.id not in {item.id for item in allowed}:
            raise NotFoundError("Resource not found")
        return report

    async def _validate_recipient_scope(
        self,
        *,
        elder_id: UUID,
        report_type: str,
        relationship_ids: list[UUID],
        consent_id: UUID,
    ) -> list[UUID]:
        now = datetime.now(UTC)
        required_scope = REPORT_SCOPE[report_type]
        validated: list[UUID] = []
        for relationship_id in relationship_ids:
            relationship = await self._reports.get_family_relationship(
                relationship_id=relationship_id,
                elder_id=elder_id,
                actor_id=None,
                current_time=now,
            )
            if (
                relationship is None
                or relationship.consent_id != consent_id
                or (
                    required_scope not in relationship.share_scope
                    and "REPORT_ALL" not in relationship.share_scope
                )
            ):
                raise ValidationError(
                    details=[
                        {
                            "field": "recipient_scope_ids",
                            "reason": "recipient relationship or share scope is not active",
                        }
                    ]
                )
            validated.append(relationship.id)
        return validated

    async def _validate_sources(
        self,
        *,
        elder_id: UUID,
        source_event_ids: list[UUID],
        source_summary_ids: list[UUID],
    ) -> None:
        if source_event_ids:
            event_count = await self._session.scalar(
                select(func.count())
                .select_from(CareEvent)
                .where(
                    CareEvent.id.in_(source_event_ids),
                    CareEvent.elder_id == elder_id,
                    CareEvent.tenant_id == self._tenant_id,
                    CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
                )
            )
            if event_count != len(set(source_event_ids)):
                raise ValidationError(
                    details=[
                        {
                            "field": "source_event_ids",
                            "reason": "family reports can use only verified events",
                        }
                    ]
                )
        if source_summary_ids:
            summary_count = await self._session.scalar(
                select(func.count())
                .select_from(DailySummary)
                .where(
                    DailySummary.id.in_(source_summary_ids),
                    DailySummary.elder_id == elder_id,
                    DailySummary.tenant_id == self._tenant_id,
                    DailySummary.status.in_(["READY", "PUBLISHED"]),
                )
            )
            if summary_count != len(set(source_summary_ids)):
                raise ValidationError(
                    details=[
                        {
                            "field": "source_summary_ids",
                            "reason": "family reports can use only ready or published summaries",
                        }
                    ]
                )

    async def _write_event(
        self,
        *,
        event_type: str,
        report: FamilyReport,
        actor_id: UUID,
        consent_version: int | None,
        trace_id: str,
        idempotency_key: str,
        extra_payload: dict | None = None,
    ) -> None:
        payload = {
            "report_id": str(report.id),
            "status": report.status,
            "version": report.current_version,
        }
        payload.update(extra_payload or {})
        await write_outbox_entry(
            self._session,
            event_type=event_type,
            aggregate_type="family_report",
            aggregate_id=report.id,
            aggregate_version=report.current_version,
            tenant_id=self._tenant_id,
            elder_id=report.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.FAMILY_SHARING.value,
            consent_version=consent_version,
            payload=payload,
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
