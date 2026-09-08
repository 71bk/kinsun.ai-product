"""Summary dashboard privacy, visibility, and bounded metadata query."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.domain.summary_visibility import ALLOWED_SUMMARY_STATUSES, FORMAL_SUMMARY_STATUSES
from app.repositories.summary_repo import DailySummarySnapshot, SummaryRepository
from app.services import dashboard_service


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["FAMILY_MEMBER", "ELDER", "ADMIN", "SYSTEM_SERVICE"])
async def test_nonprofessionals_never_query_summaries(role, monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role=role)
    auth, session = AsyncMock(), AsyncMock()
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    assert (
        await dashboard_service.get_daily_summary_snapshots(
            session, actor, [uuid4()], datetime.now(UTC)
        )
        == {}
    )
    auth.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_gate_required_review_gate_optional_and_deduplicated(monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="HOME_CARE_WORKER")
    reviewer, reader, denied, unrelated = [uuid4() for _ in range(4)]
    now = datetime.now(UTC)
    empty = DailySummarySnapshot(now.date(), "UTC", now, None)

    async def authorize(session, actor, elder, scope):
        if elder == denied or (elder == reader and scope == "summary:review"):
            raise NotFoundError("Resource not found")

    auth = AsyncMock(side_effect=authorize)
    query = AsyncMock(return_value={reviewer: empty, reader: empty, unrelated: empty})
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    monkeypatch.setattr(SummaryRepository, "dashboard_snapshots", query)
    assert await dashboard_service.get_daily_summary_snapshots(
        AsyncMock(), actor, [reviewer, reader, denied, reviewer], now
    ) == {reviewer: empty, reader: empty}
    query.assert_awaited_once_with([reviewer, reader], [reviewer], now)
    assert [call.args[3] for call in auth.await_args_list] == [
        "summary:read",
        "summary:review",
        "summary:read",
        "summary:review",
        "summary:read",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["read", "review", "query"])
async def test_operational_failure_is_not_absent_summary(failure, monkeypatch):
    actor = ActorContext(actor_id=uuid4(), tenant_id=uuid4(), actor_role="DAYCARE_CARE_WORKER")
    auth = AsyncMock(
        side_effect=[RuntimeError()]
        if failure == "read"
        else [None, RuntimeError()]
        if failure == "review"
        else [None, None]
    )
    monkeypatch.setattr(dashboard_service, "authorize_elder", auth)
    monkeypatch.setattr(
        SummaryRepository, "dashboard_snapshots", AsyncMock(side_effect=RuntimeError)
    )
    with pytest.raises(RuntimeError):
        await dashboard_service.get_daily_summary_snapshots(
            AsyncMock(), actor, [uuid4()], datetime.now(UTC)
        )


@pytest.mark.asyncio
async def test_snapshot_query_has_scoped_outer_join_without_content_or_list_limit():
    tenant, elder, summary = uuid4(), uuid4(), uuid4()
    now = datetime(2026, 9, 8, 16, tzinfo=UTC)
    session, result = AsyncMock(), MagicMock()
    session.execute.return_value = result
    repo = SummaryRepository(session, tenant)
    assert await repo.dashboard_snapshots([], [], now) == {}
    session.execute.assert_not_awaited()
    for status in [None, *sorted(ALLOWED_SUMMARY_STATUSES)]:
        result.all.return_value = [
            (
                elder,
                date(2026, 9, 9),
                "Asia/Taipei",
                summary if status else None,
                status,
                3 if status else None,
            )
        ]
        actual = (await repo.dashboard_snapshots([elder], [elder], now))[elder]
        assert actual.local_date == date(2026, 9, 9)
        assert (actual.summary.status if actual.summary else None) == status
    query = session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    assert tenant in query.params.values() and [elder] in query.params.values()
    assert now in query.params.values() and "PROFESSIONAL_DAILY" in query.params.values()
    assert list(FORMAL_SUMMARY_STATUSES) in query.params.values()
    sql = str(query)
    assert "LEFT OUTER JOIN" in sql and "timezone(" in sql and " OR " in sql
    assert all(
        term not in sql for term in ["summary_version", "content", "source_event_ids", "LIMIT"]
    )
