"""Deterministic medical boundary for AI-proposed Care Actions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.schemas.care_action import AgentCareActionCandidateProposal

_ALLOWED_ACTIONS_BY_EVENT = {
    "EXPECTED_CONTACT_MISSED": frozenset(
        {"CONTACT_ELDER", "CONTACT_FAMILY", "CONFIRM_INFORMATION", "FOLLOW_UP"}
    ),
    "ACTIVITY_CANCELLED": frozenset({"CONFIRM_INFORMATION", "INVITE_ACTIVITY", "FOLLOW_UP"}),
    "COMPANIONSHIP_NEED": frozenset({"CONTACT_ELDER", "FOLLOW_UP"}),
}

_MEDICAL_ACTION_PATTERN = re.compile(
    r"(?:停(?:用|掉)?[^。；，,\n]{0,6}藥|改藥|換藥|加藥|減藥|開藥|處方|"
    r"(?:調整|調高|調低|增加|降低)[^。；，,\n]{0,6}(?:藥|劑量)|診斷|確診|"
    r"(?:修改|變更|調整)[^。；，,\n]{0,6}照護計畫|"
    r"照護計畫[^。；，,\n]{0,6}(?:修改|變更|調整)|"
    r"(?:stop|discontinue|change|switch|start|increase|decrease)\s+"
    r"(?:the\s+)?(?:medication|medicine|drug)|"
    r"(?:adjust|increase|decrease|change)\s+(?:the\s+)?(?:dosage|dose)|"
    r"diagnos(?:e|is)|prescrib(?:e|ing)|prescription|"
    r"(?:modify|change|update|adjust)\s+(?:the\s+)?care\s+plan)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CareActionCandidatePolicyDecision:
    accepted: bool
    reason_code: str


def evaluate_care_action_candidate(
    proposal: AgentCareActionCandidateProposal,
    *,
    source_event_type: str,
    now: datetime | None = None,
) -> CareActionCandidatePolicyDecision:
    """Allow only bounded non-medical follow-up proposals for supported event types."""
    current = now or datetime.now(UTC)
    allowed_actions = _ALLOWED_ACTIONS_BY_EVENT.get(source_event_type)
    if allowed_actions is None or proposal.action_type not in allowed_actions:
        return CareActionCandidatePolicyDecision(False, "SOURCE_ACTION_NOT_ALLOWED")
    if _MEDICAL_ACTION_PATTERN.search(f"{proposal.suggested_title}\n{proposal.trigger_reason}"):
        return CareActionCandidatePolicyDecision(False, "MEDICAL_ACTION_NOT_ALLOWED")
    if proposal.suggested_due_at <= current:
        return CareActionCandidatePolicyDecision(False, "SUGGESTED_DUE_AT_NOT_FUTURE")
    if proposal.suggested_due_at > current + timedelta(days=30):
        return CareActionCandidatePolicyDecision(False, "SUGGESTED_DUE_AT_OUT_OF_RANGE")
    return CareActionCandidatePolicyDecision(True, "CANDIDATE_ALLOWED")
