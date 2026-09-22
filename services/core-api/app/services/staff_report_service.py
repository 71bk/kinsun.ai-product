"""Human-operated daily family reports from a version-checked reviewed summary."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError as SchemaValidationError
from sqlalchemy import select

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domain.consent import ConsentPurpose
from app.models.summary import DailySummary
from app.repositories.summary_repo import SummaryRepository
from app.schemas.report import (
    CreateFamilyReportDraftRequest,
    CreateReportFromSummaryRequest,
    FamilyReportItem,
    ReportRecipientResponse,
    ReportType,
)
from app.schemas.summary import SummaryItem
from app.services.consent_service import ConsentService
from app.services.report_service import ReportService


class StaffReportService(ReportService):
    async def recipients(self, elder_id: UUID) -> list[ReportRecipientResponse]:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.FAMILY_SHARING,
        )
        rows = await self._reports.list_daily_recipients(elder_id, consent.id, datetime.now(UTC))
        if len(rows) > 32:
            raise ValidationError(
                details=[
                    {"field": "recipient_scope_ids", "reason": "REPORT_RECIPIENT_LIMIT_EXCEEDED"}
                ]
            )
        return [
            ReportRecipientResponse(
                relationship_id=relationship.id,
                display_name=name,
                share_scope=relationship.share_scope,
            )
            for relationship, name in rows
        ]

    async def create_from_summary(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateReportFromSummaryRequest,
        trace_id: str,
        idempotency_key: str,
    ):
        for purpose in (ConsentPurpose.FAMILY_SHARING, ConsentPurpose.CARE_EVENT_EXTRACTION):
            await ConsentService(self._session, self._tenant_id).require_active(
                elder_id=elder_id,
                purpose=purpose,
            )
        result = await self._session.execute(
            select(DailySummary)
            .where(
                DailySummary.id == request.summary_id,
                DailySummary.elder_id == elder_id,
                DailySummary.tenant_id == self._tenant_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        summary = result.scalar_one_or_none()
        if summary is None:
            raise NotFoundError("Resource not found")
        if summary.current_version != request.expected_summary_version or summary.status not in {
            "READY",
            "PUBLISHED",
        }:
            raise ConflictError("Summary is no longer reviewed at this version")
        source = await SummaryRepository(self._session, self._tenant_id).get_current_version(
            summary
        )
        if source.content.get("conflict_flags"):
            raise ConflictError("Summary has unresolved conflicts")
        try:
            items = [SummaryItem.model_validate(item) for item in source.content.get("items", [])]
        except SchemaValidationError as exc:
            raise ConflictError("Summary content requires review") from exc
        source_events = list(dict.fromkeys(eid for item in items for eid in item.source_event_ids))
        if len(source_events) > 64 or len(items) > 64:
            raise ValidationError(
                details=[{"field": "summary_id", "reason": "REPORT_SOURCE_LIMIT_EXCEEDED"}]
            )
        if any(item.data_status != "PRESENT" for item in items):
            raise ConflictError("Summary contains unresolved items")
        draft = CreateFamilyReportDraftRequest(
            recipient_scope_ids=list(dict.fromkeys(request.recipient_scope_ids)),
            report_type=ReportType.DAILY,
            period_start=summary.summary_date,
            period_end=summary.summary_date,
            items=[
                FamilyReportItem(category=item.category, text=item.text, source_ids=[summary.id])
                for item in items
            ],
            source_summary_ids=[summary.id],
            source_event_ids=source_events,
            data_gap_notice=(
                "部分生活項目沒有足夠資料；未提及不代表沒有發生。"
                if source.content.get("missing_fields") or not items
                else None
            ),
            sensitive_review_required=True,
        )
        return await self.create_draft(
            elder_id=elder_id,
            actor_id=actor_id,
            request=draft,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            source_summary_versions={str(summary.id): summary.current_version},
        )
