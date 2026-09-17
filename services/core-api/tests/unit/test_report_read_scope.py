"""Fresh family reads must honor the current report-type sharing scope."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api import reports
from app.api.error_handlers import register_exception_handlers
from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError, ValidationError
from app.services import report_service
from app.services.report_service import REPORT_SCOPE, ReportService


@pytest.fixture
def data(monkeypatch):
    tenant, elder, actor, consent, recipient = (uuid4() for _ in range(5))
    now = datetime.now(UTC)
    report = SimpleNamespace(
        id=uuid4(),
        elder_id=elder,
        tenant_id=tenant,
        report_type="DAILY",
        status="PUBLISHED",
        recipient_scope={"relationship_ids": [str(recipient)]},
        period_start=date.today(),
        period_end=date.today(),
        current_version=1,
        published_at=now,
        withdrawn_at=None,
        updated_at=now,
    )
    relationship = SimpleNamespace(consent_id=consent, share_scope=["REPORT_DAILY"])
    repo = SimpleNamespace(
        get=AsyncMock(return_value=report),
        list_published=AsyncMock(return_value=[report]),
        get_family_relationship=AsyncMock(return_value=relationship),
        get_current_version=AsyncMock(return_value=SimpleNamespace(content={"items": []})),
    )
    consent_service = SimpleNamespace(
        require_active=AsyncMock(return_value=SimpleNamespace(id=consent))
    )
    monkeypatch.setattr(report_service, "ReportRepository", MagicMock(return_value=repo))
    monkeypatch.setattr(report_service, "ConsentService", MagicMock(return_value=consent_service))
    return SimpleNamespace(
        tenant=tenant,
        elder=elder,
        actor=actor,
        recipient=recipient,
        report=report,
        relationship=relationship,
        repo=repo,
        consent_service=consent_service,
        session=MagicMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("report_type,scope", REPORT_SCOPE.items())
async def test_list_and_detail_recheck_type_after_scope_is_narrowed(data, report_type, scope):
    data.report.report_type = report_type
    data.relationship.share_scope = ["REPORT_ALL"]
    service = ReportService(data.session, data.tenant)
    assert (
        await service.get_for_family(report_id=data.report.id, actor_id=data.actor) is data.report
    )
    data.relationship.share_scope = [scope]
    assert (
        await service.get_for_family(report_id=data.report.id, actor_id=data.actor) is data.report
    )
    data.relationship.share_scope = [value for value in REPORT_SCOPE.values() if value != scope]
    assert (
        await service.list_for_family(elder_id=data.elder, actor_id=data.actor, report_type=None)
        == []
    )
    with pytest.raises(NotFoundError):
        await service.get_for_family(report_id=data.report.id, actor_id=data.actor)
    lookup = data.repo.get_family_relationship.await_args.kwargs
    assert lookup["elder_id"] == data.elder and lookup["actor_id"] == data.actor
    assert lookup["relationship_id"] == data.recipient
    data.session.flush.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["expired", "different_consent", "unknown_type", "empty_scope"])
async def test_no_scope_fallback(data, case):
    if case == "expired":
        data.repo.get_family_relationship.return_value = None
    elif case == "different_consent":
        data.relationship.consent_id = uuid4()
    elif case == "unknown_type":
        data.report.report_type = "UNKNOWN"
        data.relationship.share_scope = ["REPORT_ALL"]
    else:
        data.relationship.share_scope = []
    service = ReportService(data.session, data.tenant)
    with pytest.raises(NotFoundError):
        await service.get_for_family(report_id=data.report.id, actor_id=data.actor)


@pytest.mark.asyncio
async def test_publication_uses_same_type_policy(data):
    service = ReportService(data.session, data.tenant)
    data.relationship.share_scope = ["REPORT_WEEKLY"]
    with pytest.raises(ValidationError):
        await service._validate_recipient_scope(
            elder_id=data.elder,
            report_type="DAILY",
            relationship_ids=[data.recipient],
            consent_id=data.relationship.consent_id,
        )


@pytest.mark.asyncio
async def test_revoked_consent_stops_before_report_query(data):
    data.consent_service.require_active.side_effect = NotFoundError("Resource not found")
    with pytest.raises(NotFoundError):
        await ReportService(data.session, data.tenant).list_for_family(
            elder_id=data.elder,
            actor_id=data.actor,
            report_type=None,
        )
    data.repo.list_published.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_fresh_requests_remove_narrowed_report_and_hide_detail(data, monkeypatch):
    app = FastAPI()
    app.include_router(reports.router)
    register_exception_handlers(app)
    actor = ActorContext(actor_id=data.actor, tenant_id=data.tenant, actor_role="FAMILY_MEMBER")
    app.dependency_overrides[reports.require_active_actor] = lambda: actor
    app.dependency_overrides[reports.get_db_session] = lambda: data.session
    monkeypatch.setattr(reports, "authorize_elder", AsyncMock())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listing = f"/api/v1/family/elders/{data.elder}/reports"
        detail = f"/api/v1/family/reports/{data.report.id}"
        assert (await client.get(detail)).status_code == 200
        assert len((await client.get(listing)).json()["data"]["items"]) == 1
        data.relationship.share_scope = ["REPORT_WEEKLY"]
        assert (await client.get(listing)).json()["data"]["items"] == []
        denied = await client.get(detail)
        assert denied.status_code == 404
        assert str(data.report.id) not in denied.text
        data.repo.get.return_value = None
        absent = await client.get(detail)
        assert absent.json()["error"]["code"] == denied.json()["error"]["code"]
