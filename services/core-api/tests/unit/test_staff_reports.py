"""Staff report role, scope, consent and input guard tests without a database."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api import staff_reports
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.schemas.report import CreateReportFromSummaryRequest, PublishFamilyReportRequest
from app.services.staff_report_service import StaffReportService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role", ["ELDER", "FAMILY_MEMBER", "ADMIN", "SYSTEM_SERVICE", "CONTENT_MANAGER"]
)
async def test_non_staff_roles_cannot_use_staff_reports(role):
    with pytest.raises(NotFoundError):
        await staff_reports.require_report_staff(
            ActorContext(
                actor_id=uuid4(),
                actor_role=role,
                tenant_id=uuid4(),
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["DAYCARE_CARE_WORKER", "HOME_CARE_WORKER"])
async def test_staff_role_guard_does_not_replace_elder_scope(role):
    actor = ActorContext(actor_id=uuid4(), actor_role=role, tenant_id=uuid4())
    assert await staff_reports.require_report_staff(actor) is actor


@pytest.mark.asyncio
async def test_missing_scope_denies_before_reading_recipients_or_reports(monkeypatch):
    monkeypatch.setattr(staff_reports, "authorize_elder", AsyncMock(side_effect=NotFoundError()))
    service = MagicMock()
    monkeypatch.setattr(staff_reports, "StaffReportService", service)
    with pytest.raises(NotFoundError):
        await staff_reports.report_workspace(
            elder_id=uuid4(),
            session=MagicMock(),
            actor=ActorContext(actor_id=uuid4(), actor_role="HOME_CARE_WORKER", tenant_id=uuid4()),
        )
    service.assert_not_called()


@pytest.mark.asyncio
async def test_inactive_consent_denies_before_reading_summary(monkeypatch):
    monkeypatch.setattr(
        "app.services.staff_report_service.ConsentService.require_active",
        AsyncMock(side_effect=NotFoundError()),
    )
    session = MagicMock()
    session.execute = AsyncMock()
    with pytest.raises(NotFoundError):
        await StaffReportService(session, uuid4()).create_from_summary(
            elder_id=uuid4(),
            actor_id=uuid4(),
            trace_id="synthetic",
            idempotency_key="synthetic",
            request=CreateReportFromSummaryRequest(
                summary_id=uuid4(), expected_summary_version=1, recipient_scope_ids=[uuid4()]
            ),
        )
    session.execute.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.parametrize("extra", ["items", "tenant_id", "actor_id", "safety_review_passed"])
def test_browser_cannot_inject_content_identity_or_review_into_draft(extra):
    with pytest.raises(ValidationError):
        CreateReportFromSummaryRequest.model_validate(
            {
                "summary_id": str(uuid4()),
                "expected_summary_version": 1,
                "recipient_scope_ids": [str(uuid4())],
                extra: "untrusted",
            }
        )


def test_publish_requires_explicit_positive_review():
    for value in [False, None]:
        with pytest.raises(ValidationError):
            PublishFamilyReportRequest(
                expected_version=1, safety_review_passed=value, reason_code="SYNTHETIC_REVIEW"
            )


@pytest.mark.asyncio
async def test_command_locks_report_before_idempotency_and_scope_denial_prevents_lock(monkeypatch):
    order = []

    async def authorize(*args):
        order.append("authorize")

    async def lock(*args):
        order.append("lock")
        return None

    monkeypatch.setattr(staff_reports, "authorize_elder", authorize)
    service = SimpleNamespace(_reports=SimpleNamespace(get_for_update=lock))
    monkeypatch.setattr(staff_reports, "StaffReportService", MagicMock(return_value=service))
    idem = MagicMock()
    monkeypatch.setattr(staff_reports, "IdempotencyRepository", idem)
    with pytest.raises(NotFoundError):
        await staff_reports.staff_report_command(
            elder_id=uuid4(),
            report_id=uuid4(),
            operation="publish",
            request=PublishFamilyReportRequest(
                expected_version=1, safety_review_passed=True, reason_code="SYNTHETIC_REVIEW"
            ),
            idempotency_key="synthetic",
            session=MagicMock(),
            actor=ActorContext(actor_id=uuid4(), actor_role="HOME_CARE_WORKER", tenant_id=uuid4()),
        )
    assert order == ["authorize", "lock"]
    idem.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_content", [True, False])
async def test_invalid_or_oversized_summary_cannot_create_a_partial_report(
    monkeypatch, invalid_content
):
    from datetime import date

    from app.core.exceptions import ConflictError
    from app.core.exceptions import ValidationError as DomainValidationError
    from app.repositories.summary_repo import SummaryRepository

    monkeypatch.setattr(
        "app.services.staff_report_service.ConsentService.require_active",
        AsyncMock(return_value=SimpleNamespace(id=uuid4(), version=1)),
    )
    summary = SimpleNamespace(
        id=uuid4(), status="READY", current_version=1, summary_date=date.today()
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = summary
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    items = [
        {
            "category": "MEAL",
            "text": "Synthetic reviewed meal",
            "data_status": "PRESENT",
            "source_event_ids": [str(uuid4()), str(uuid4()), str(uuid4())],
        }
        for _ in range(32)
    ]
    if invalid_content:
        items[0]["source_event_ids"] = []
    monkeypatch.setattr(
        SummaryRepository,
        "get_current_version",
        AsyncMock(return_value=SimpleNamespace(content={"items": items, "conflict_flags": []})),
    )
    service = StaffReportService(session, uuid4())
    service.create_draft = AsyncMock()
    with pytest.raises(ConflictError if invalid_content else DomainValidationError):
        await service.create_from_summary(
            elder_id=uuid4(),
            actor_id=uuid4(),
            trace_id="synthetic",
            idempotency_key="synthetic",
            request=CreateReportFromSummaryRequest(
                summary_id=summary.id, expected_summary_version=1, recipient_scope_ids=[uuid4()]
            ),
        )
    service.create_draft.assert_not_awaited()
