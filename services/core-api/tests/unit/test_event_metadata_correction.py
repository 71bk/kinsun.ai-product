"""Correction validation, audit preservation and idempotency compatibility."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from app.api import care_events
from app.core.auth import ActorContext
from app.core.exceptions import ConflictError
from app.models.care_event import CareEvent, CareEventVersion
from app.schemas.care_event import ReviewCareEventRequest
from app.services import care_event_service
from app.services.care_event_service import CareEventService

BASE = {
    "decision": "CORRECT",
    "reason_code": "SYNTHETIC",
    "corrected_payload": {},
    "expected_version": 1,
}


@pytest.mark.parametrize(
    ("extra", "valid"),
    [
        ({}, True),
        ({"corrected_event_type": "SLEEP"}, True),
        ({"corrected_event_time": None}, True),
        ({"corrected_event_time": "2026-09-15T08:00:00+08:00"}, True),
        ({"corrected_event_time": "2026-09-15T08:00:00"}, False),
        ({"corrected_event_type": None}, False),
        ({"corrected_event_type": "DIAGNOSIS"}, False),
        ({"decision": "VERIFY", "corrected_payload": None, "corrected_event_time": None}, False),
        ({"decision": "REJECT", "corrected_payload": None, "corrected_event_type": "SLEEP"}, False),
        ({"decision": "EXCLUDE", "corrected_payload": None, "corrected_event_time": None}, False),
    ],
)
def test_schema_and_contract_agree(extra, valid):
    payload = {**BASE, **extra}
    schema_path = (
        Path(__file__).resolve().parents[4]
        / "contracts/schemas/domain/ReviewCareEventRequestV1.json"
    )
    validator = Draft202012Validator(
        json.loads(schema_path.read_text(encoding="utf-8")), format_checker=FormatChecker()
    )
    assert validator.is_valid(payload) is valid
    if valid:
        ReviewCareEventRequest.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            ReviewCareEventRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_review_fingerprint_preserves_old_payload_and_distinguishes_clear(monkeypatch):
    actor = ActorContext(uuid4(), "HOME_CARE_WORKER", uuid4())
    elder_id, event_id = uuid4(), uuid4()
    idem = SimpleNamespace(
        begin=AsyncMock(return_value=SimpleNamespace(replayed=True, response_body={"saved": True}))
    )
    monkeypatch.setattr(care_events, "authorize_elder", AsyncMock())
    monkeypatch.setattr(care_events, "IdempotencyRepository", MagicMock(return_value=idem))
    for extra in ({}, {"corrected_event_time": None}):
        await care_events.review_care_event(
            ReviewCareEventRequest(**BASE, **extra),
            elder_id,
            event_id,
            "same-key",
            actor,
            MagicMock(),
        )
    old, cleared = [call.kwargs["payload"] for call in idem.begin.await_args_list]
    assert old == {"elder_id": elder_id, "event_id": event_id, **BASE}
    assert cleared == {**old, "corrected_event_time": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"corrected_event_time": None},
        {"corrected_event_type": "SLEEP", "corrected_event_time": "2026-09-14T20:00:00Z"},
    ],
)
async def test_correction_preserves_metadata_payload_and_audit(monkeypatch, extra):
    actor = ActorContext(uuid4(), "HOME_CARE_WORKER", uuid4())
    old_time = datetime(2026, 9, 15, tzinfo=UTC)
    event = CareEvent(
        id=uuid4(),
        elder_id=uuid4(),
        tenant_id=actor.tenant_id,
        event_type="MEAL",
        event_time=old_time,
        status="NEEDS_REVIEW",
        current_version=1,
        consent_version=1,
    )
    old = CareEventVersion(
        event_version_id=uuid4(),
        event_id=event.id,
        version=1,
        structured_payload={"text": "Synthetic original"},
    )
    repository = SimpleNamespace(
        get_current_version=AsyncMock(return_value=old),
        add_version=MagicMock(),
        add_review=MagicMock(),
    )
    session = MagicMock(flush=AsyncMock(), execute=AsyncMock())
    service = CareEventService(session, actor.tenant_id)
    service._events = repository
    monkeypatch.setattr(
        care_event_service,
        "ConsentService",
        MagicMock(return_value=SimpleNamespace(require_active=AsyncMock())),
    )
    outbox = AsyncMock()
    monkeypatch.setattr(care_event_service, "write_outbox_entry", outbox)
    request = ReviewCareEventRequest(**BASE, **extra)
    review, rebuild = await service.review(
        event=event, actor_context=actor, request=request, trace_id="test", idempotency_key="test"
    )
    assert review.before_event_type == "MEAL" and review.before_event_time == old_time
    assert review.after_event_type == event.event_type == extra.get("corrected_event_type", "MEAL")
    expected_time = request.corrected_event_time if "corrected_event_time" in extra else old_time
    assert review.after_event_time == event.event_time == expected_time
    assert (review.before_version, review.after_version, event.current_version) == (1, 2, 2)
    new = repository.add_version.call_args.args[0]
    assert new.supersedes_version_id == old.event_version_id and new.structured_payload == {}
    assert old.structured_payload == {"text": "Synthetic original"}
    assert new.memory_candidate_proposal is None and new.care_action_candidate_proposal is None
    assert rebuild == ["DAILY_SUMMARY"] and event.status == "CORRECTED"
    assert set(outbox.await_args.kwargs["payload"]) == {
        "event_id",
        "status",
        "version",
        "review_id",
    }
    with pytest.raises(ConflictError):
        await service.review(
            event=event,
            actor_context=actor,
            request=request,
            trace_id="test",
            idempotency_key="other",
        )
