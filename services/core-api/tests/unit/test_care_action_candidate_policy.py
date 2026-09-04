from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.policies.care_action_candidate_policy import evaluate_care_action_candidate
from app.schemas.care_action import AgentCareActionCandidateProposal

NOW = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)


def _proposal(**overrides: object) -> AgentCareActionCandidateProposal:
    values: dict[str, object] = {
        "action_type": "CONTACT_FAMILY",
        "suggested_title": "確認預期聯繫狀況",
        "trigger_reason": "預期聯繫未發生，需要由照護者確認。",
        "suggested_due_at": NOW + timedelta(days=1),
        "priority": "MEDIUM",
        "extractor_version": "care-action-candidate-v1",
    }
    values.update(overrides)
    return AgentCareActionCandidateProposal.model_validate(values)


def test_matching_non_medical_follow_up_is_allowed() -> None:
    decision = evaluate_care_action_candidate(
        _proposal(),
        source_event_type="EXPECTED_CONTACT_MISSED",
        now=NOW,
    )

    assert decision.accepted is True
    assert decision.reason_code == "CANDIDATE_ALLOWED"


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "請家屬幫長者停藥",
        "聯繫後直接調高藥物劑量",
        "替長者確診失智症",
        "自動修改照護計畫",
        "Ask the family to discontinue the medication",
        "Increase the dose without another review",
        "Diagnose dementia",
        "Update the care plan automatically",
    ],
)
def test_medical_or_automatic_plan_action_is_rejected(unsafe_text: str) -> None:
    decision = evaluate_care_action_candidate(
        _proposal(trigger_reason=unsafe_text),
        source_event_type="EXPECTED_CONTACT_MISSED",
        now=NOW,
    )

    assert decision.accepted is False
    assert decision.reason_code == "MEDICAL_ACTION_NOT_ALLOWED"


def test_source_event_and_action_pair_must_be_allowlisted() -> None:
    decision = evaluate_care_action_candidate(
        _proposal(action_type="INVITE_ACTIVITY"),
        source_event_type="EXPECTED_CONTACT_MISSED",
        now=NOW,
    )

    assert decision.accepted is False
    assert decision.reason_code == "SOURCE_ACTION_NOT_ALLOWED"


@pytest.mark.parametrize(
    ("due_at", "reason_code"),
    [
        (NOW, "SUGGESTED_DUE_AT_NOT_FUTURE"),
        (NOW + timedelta(days=31), "SUGGESTED_DUE_AT_OUT_OF_RANGE"),
    ],
)
def test_suggested_due_at_is_bounded(due_at: datetime, reason_code: str) -> None:
    decision = evaluate_care_action_candidate(
        _proposal(suggested_due_at=due_at),
        source_event_type="EXPECTED_CONTACT_MISSED",
        now=NOW,
    )

    assert decision.accepted is False
    assert decision.reason_code == reason_code
