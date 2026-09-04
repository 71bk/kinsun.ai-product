"""Application-facing boundary for the private Agent Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class AgentSafetyResult:
    """Validated safety decision returned by the runtime adapter."""

    schema_version: str
    decision: str
    risk_level: str
    reason_codes: list[str]
    matched_terms: list[str]
    safe_reply: str | None


@dataclass(frozen=True)
class AgentEventCandidateProposal:
    """Minimized untrusted event proposal with no Core-owned scope facts."""

    event_type: str
    event_time: datetime | None
    structured_payload: dict[str, object]
    evidence_refs: list[str]
    confidence_band: str
    review_requirement: str
    extractor_version: str


@dataclass(frozen=True)
class AgentMemoryCandidateProposal:
    """Minimized untrusted memory proposal with no Core-owned scope facts."""

    memory_type: str
    memory_kind: str
    normalized_content: str
    confirmation_question: str
    extraction_confidence: float
    proposal_risk_hint: str
    extractor_version: str

    def as_payload(self) -> dict[str, object]:
        """Return the proposal fields accepted by the Core policy boundary."""
        return {
            "memory_type": self.memory_type,
            "memory_kind": self.memory_kind,
            "normalized_content": self.normalized_content,
            "confirmation_question": self.confirmation_question,
            "extraction_confidence": self.extraction_confidence,
            "proposal_risk_hint": self.proposal_risk_hint,
            "extractor_version": self.extractor_version,
        }


@dataclass(frozen=True)
class AgentCareActionCandidateProposal:
    """Minimized untrusted action proposal with no Core-owned source facts."""

    action_type: str
    suggested_title: str
    trigger_reason: str
    suggested_due_at: datetime
    priority: str
    extractor_version: str

    def as_payload(self) -> dict[str, object]:
        return {
            "action_type": self.action_type,
            "suggested_title": self.suggested_title,
            "trigger_reason": self.trigger_reason,
            "suggested_due_at": self.suggested_due_at,
            "priority": self.priority,
            "extractor_version": self.extractor_version,
        }


@dataclass(frozen=True)
class AgentRunResult:
    """Transport-neutral result consumed by Core application services."""

    schema_version: str
    request_id: str
    trace_id: str
    agent_run_id: str
    selected_agent: str
    reply_text: str
    reply_language: str
    safety_result: AgentSafetyResult
    context_manifest_id: str
    step_count: int
    result_status: str
    reason_codes: list[str]
    event_candidate_proposal: AgentEventCandidateProposal | None = None
    memory_candidate_proposal: AgentMemoryCandidateProposal | None = None
    care_action_candidate_proposal: AgentCareActionCandidateProposal | None = None


class AgentRuntimePort(Protocol):
    """Port used by Core services to execute one bounded Agent run."""

    async def run(
        self,
        *,
        request_payload: dict[str, object],
        correlation_id: str,
    ) -> AgentRunResult:
        """Execute one run using an adapter-selected transport."""
        ...
