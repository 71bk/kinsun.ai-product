"""Daily summaries are deterministic views of reviewed formal events."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.care_event_rendering import render_reviewed_event
from app.services.summary_service import SummaryService


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
