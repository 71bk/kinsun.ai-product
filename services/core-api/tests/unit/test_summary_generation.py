"""Daily summaries are deterministic views of reviewed formal events."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.summary import DailySummary
from app.services.care_event_rendering import render_reviewed_event
from app.services.summary_service import SummaryService


def test_summary_update_keeps_response_timestamp_loaded() -> None:
    """Real ORM flush using SQLite; PostgreSQL workflow is tested separately."""
    engine = create_engine(
        "sqlite://", execution_options={"schema_translate_map": {"eldercare_ai": None}}
    )
    try:
        DailySummary.__table__.create(engine)
        with Session(engine, expire_on_commit=False) as session:
            summary = DailySummary(
                id=uuid4(),
                tenant_id=uuid4(),
                elder_id=uuid4(),
                summary_date=date(2026, 8, 14),
                summary_type="PROFESSIONAL_DAILY",
                status="NEEDS_REVIEW",
                current_version=1,
            )
            session.add(summary)
            session.flush()
            summary.status = "STALE"
            session.flush()
            assert "updated_at" not in inspect(summary).expired_attributes
            assert isinstance(summary.updated_at, datetime)
    finally:
        engine.dispose()


def test_reviewed_event_renderer_does_not_infer_missing_details() -> None:
    assert render_reviewed_event("SLEEP", {}) == "睡眠陳述：已有一筆人工覆核紀錄。"
    assert (
        render_reviewed_event("MEAL", {"summary": "早餐吃了粥", "diagnosis": "must-ignore"})
        == "飲食紀錄：早餐吃了粥"
    )


@pytest.mark.asyncio
async def test_generation_uses_only_verified_current_events_and_source_ids() -> None:
    elder_id = uuid4()
    actor_id = uuid4()
    event_id = uuid4()
    event = SimpleNamespace(id=event_id, event_type="MEAL")
    version = SimpleNamespace(structured_payload={"summary": "早餐吃了粥"})
    result = MagicMock()
    result.all.return_value = [(event, version)]
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    service = SummaryService(session, uuid4())
    created = SimpleNamespace(id=uuid4())
    service.create_draft = AsyncMock(return_value=created)  # type: ignore[method-assign]

    returned = await service.generate_from_verified_events(
        elder_id=elder_id,
        actor_id=actor_id,
        summary_date=date(2026, 8, 14),
        trace_id="trace-summary-generate",
        idempotency_key="summary-generate-001",
    )

    assert returned is created
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": False}))
    assert "care_event.status IN" in compiled
    assert "care_event.tenant_id" in compiled
    assert "care_event.elder_id" in compiled
    assert "care_event_version.version = eldercare_ai.care_event.current_version" in compiled
    request = service.create_draft.await_args.kwargs["request"]
    assert request.model_version == "deterministic-summary-v1"
    assert request.items[0].text == "飲食紀錄：早餐吃了粥"
    assert request.items[0].source_event_ids == [event_id]
    assert "MEAL" not in request.missing_fields
    assert "SLEEP" in request.missing_fields


@pytest.mark.asyncio
async def test_no_verified_events_produces_explicit_not_mentioned_fields() -> None:
    result = MagicMock()
    result.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    service = SummaryService(session, uuid4())
    service.create_draft = AsyncMock(return_value=SimpleNamespace(id=uuid4()))  # type: ignore[method-assign]

    await service.generate_from_verified_events(
        elder_id=uuid4(),
        actor_id=uuid4(),
        summary_date=date(2026, 8, 14),
        trace_id="trace-summary-empty",
        idempotency_key="summary-empty-001",
    )

    request = service.create_draft.await_args.kwargs["request"]
    assert request.items == []
    assert request.missing_fields == [
        "ACTIVITY",
        "MEAL",
        "MEDICATION_STATEMENT",
        "SLEEP",
        "SOCIAL",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [31, 32, 33])
async def test_daily_event_limit_never_persists_a_truncated_summary(count: int) -> None:
    rows = [
        (
            SimpleNamespace(id=uuid4(), event_type="MEAL"),
            SimpleNamespace(structured_payload={"text": "Synthetic meal"}),
        )
        for _ in range(count)
    ]
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.execute.return_value.all.return_value = rows
    service = SummaryService(session, uuid4())
    service.create_draft = AsyncMock()
    kwargs = dict(
        elder_id=uuid4(),
        actor_id=uuid4(),
        summary_date=date(2026, 8, 14),
        trace_id="synthetic-limit",
        idempotency_key="synthetic-limit",
    )
    if count > 32:
        with pytest.raises(ValidationError) as error:
            await service.generate_from_verified_events(**kwargs)
        assert error.value.details == [
            {"field": "summary_date", "reason": "SUMMARY_EVENT_LIMIT_EXCEEDED"}
        ]
        service.create_draft.assert_not_awaited()
        session.add.assert_not_called()
        session.flush.assert_not_called()
    else:
        await service.generate_from_verified_events(**kwargs)
        request = service.create_draft.await_args.kwargs["request"]
        assert len(request.items) == count
        assert [item.source_event_ids[0] for item in request.items] == [row[0].id for row in rows]


@pytest.mark.asyncio
@pytest.mark.parametrize("day", [date(2026, 1, 1), date(2024, 2, 29), date(9999, 12, 31)])
async def test_generation_binds_complete_taipei_day_and_bounded_query(day: date) -> None:
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.execute.return_value.all.return_value = []
    tenant_id, elder_id = uuid4(), uuid4()
    service = SummaryService(session, tenant_id)
    service.create_draft = AsyncMock()
    await service.generate_from_verified_events(
        elder_id=elder_id,
        actor_id=uuid4(),
        summary_date=day,
        trace_id="synthetic-day",
        idempotency_key="synthetic-day",
    )
    statement = session.execute.await_args.args[0]
    compiled = statement.compile()
    params = compiled.params
    midnight = datetime.combine(day, datetime.min.time(), UTC)
    assert params["coalesce_1"] == midnight - timedelta(hours=8)
    assert params["coalesce_2"] == midnight + timedelta(
        hours=15, minutes=59, seconds=59, microseconds=999999
    )
    assert params["tenant_id_1"] == tenant_id
    assert params["elder_id_1"] == elder_id
    assert params["status_1"] == ["VERIFIED", "CORRECTED"]
    assert params["param_1"] == 33
    sql = str(compiled)
    assert (
        "coalesce(eldercare_ai.care_event.event_time, eldercare_ai.care_event.created_at) >=" in sql
    )
    assert (
        "coalesce(eldercare_ai.care_event.event_time, eldercare_ai.care_event.created_at) <=" in sql
    )
