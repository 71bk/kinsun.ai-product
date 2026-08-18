"""Restricted-key traversal and boundary-policy regression tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.restricted_keys import contains_restricted_key
from app.events.consumer import DomainEvent
from app.events.outbox_writer import write_outbox_entry
from app.schemas.care_event import (
    CareEventType,
    ConfidenceBand,
    CreateCareEventCandidateRequest,
    ReviewCareEventRequest,
)
from app.schemas.tool import ToolRequest


def _tool_request(parameters: dict) -> ToolRequest:
    return ToolRequest(
        tool_call_id=uuid4(),
        agent_run_id=uuid4(),
        tool_name="summary.read",
        tool_version="1.0",
        elder_id=uuid4(),
        purpose="CARE_SUMMARY",
        consent_version=1,
        policy_version="policy-v1",
        request_id="request-1",
        parameters=parameters,
    )


def _domain_event(payload: dict) -> DomainEvent:
    return DomainEvent(
        event_id=uuid4(),
        event_type="memory.confirmed.v1",
        event_version=1,
        occurred_at=datetime.now(UTC),
        tenant_id=uuid4(),
        elder_id=uuid4(),
        actor_id=uuid4(),
        purpose="LONG_TERM_MEMORY",
        consent_version=1,
        trace_id="trace-1",
        correlation_id="trace-1",
        causation_id=None,
        idempotency_key=None,
        classification="CONFIDENTIAL",
        aggregate={"type": "memory", "id": uuid4(), "version": 1},
        payload=payload,
    )


def _care_event_candidate(structured_payload: dict) -> CreateCareEventCandidateRequest:
    return CreateCareEventCandidateRequest(
        source_type="MANUAL",
        event_type=CareEventType.MEAL,
        structured_payload=structured_payload,
        confidence_band=ConfidenceBand.HIGH,
        extractor_version="extractor-v1",
    )


def test_contains_restricted_key_preserves_dict_list_and_key_only_semantics() -> None:
    forbidden_keys = {"1", "secret"}

    assert contains_restricted_key({"safe": [{"SeCrEt": "value"}]}, forbidden_keys)
    assert contains_restricted_key({1: "value"}, forbidden_keys)
    assert not contains_restricted_key({"safe": "secret"}, forbidden_keys)
    assert not contains_restricted_key(({"secret": "value"},), forbidden_keys)


def test_tool_request_rejects_nested_restricted_key_case_insensitively() -> None:
    with pytest.raises(ValidationError, match="parameters contain a restricted field"):
        _tool_request({"context": [{"SeCrEt": "value"}]})


def test_care_event_candidate_and_correction_reject_asr_confidence() -> None:
    payload = {"context": [{"ASR_CONFIDENCE": 0.91}]}

    with pytest.raises(ValidationError, match="structured_payload contains a restricted field"):
        _care_event_candidate(payload)

    with pytest.raises(ValidationError, match="corrected_payload contains a restricted field"):
        ReviewCareEventRequest(
            decision="CORRECT",
            reason_code="synthetic-correction",
            corrected_payload=payload,
            expected_version=1,
        )


@pytest.mark.asyncio
async def test_asr_confidence_remains_allowed_outside_care_event_boundary() -> None:
    payload = {"context": [{"ASR_CONFIDENCE": 0.91}]}

    assert _tool_request(payload).parameters == payload
    assert _domain_event(payload).payload == payload

    session = AsyncMock()
    await write_outbox_entry(
        session=session,
        event_type="memory.confirmed.v1",
        aggregate_type="memory",
        aggregate_id=uuid4(),
        tenant_id=uuid4(),
        payload=payload,
        trace_id="trace-1",
    )

    session.execute.assert_awaited_once()
