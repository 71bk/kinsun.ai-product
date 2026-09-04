"""Bounded non-medical Care Action proposal extraction."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from agent_runtime.contracts.models import (
    AgentRunRequest,
    CareActionCandidateProposal,
    EventCandidateProposal,
)

EXTRACTOR_VERSION = "care-action-candidate-v1"

_PROPOSALS = {
    "EXPECTED_CONTACT_MISSED": (
        "CONTACT_FAMILY",
        "確認預期聯繫狀況",
        "原始事件顯示預期聯繫未發生，需要由照護者確認。",
        1,
    ),
    "ACTIVITY_CANCELLED": (
        "FOLLOW_UP",
        "追蹤活動取消狀況",
        "原始事件顯示活動已取消，需要由照護者追蹤後續安排。",
        2,
    ),
    "COMPANIONSHIP_NEED": (
        "CONTACT_ELDER",
        "聯繫長者了解近況",
        "原始事件記錄了明確的陪伴需求，需要由照護者聯繫確認。",
        1,
    ),
}


class CareActionCandidateAgent:
    """Return at most one fixed-shape proposal and never call a Core Tool."""

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run(
        self,
        request: AgentRunRequest,
        *,
        source_event: EventCandidateProposal,
    ) -> CareActionCandidateProposal | None:
        if not request.language.lower().startswith("zh"):
            return None
        template = _PROPOSALS.get(source_event.event_type)
        if template is None:
            return None
        action_type, title, reason, due_days = template
        return CareActionCandidateProposal(
            action_type=action_type,
            suggested_title=title,
            trigger_reason=reason,
            suggested_due_at=self._clock() + timedelta(days=due_days),
            priority="MEDIUM",
            extractor_version=EXTRACTOR_VERSION,
        )
