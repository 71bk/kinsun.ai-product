from __future__ import annotations

import re

from agent_runtime.contracts.models import (
    AgentRunRequest,
    EventCandidateProposal,
    MemoryCandidateProposal,
)

EXTRACTOR_VERSION = "memory-extractor-v1"

_STABLE_BREAKFAST_ROUTINE = re.compile(
    r"(?:我)?(?:每天|每日|每天早上)(?:都|會|固定)?(?:在)?"
    r"(?:早餐|早飯)(?:都|會|固定)?(?:吃|喝)"
    r"(?P<item>粥|飯|麵|水果|豆漿|牛奶)"
)


class MemoryExtractorAgent:
    """Extract only explicit stable routines; never infer sensitive memories."""

    async def run(
        self,
        request: AgentRunRequest,
        *,
        source_event: EventCandidateProposal,
    ) -> MemoryCandidateProposal | None:
        if not request.language.lower().startswith("zh"):
            return None
        if source_event.event_type != "MEAL":
            return None

        match = _STABLE_BREAKFAST_ROUTINE.search(request.input_text.strip())
        if match is None:
            return None

        item = match.group("item")
        content = f"每天早餐習慣吃{item}。"
        if item in {"豆漿", "牛奶"}:
            content = f"每天早餐習慣喝{item}。"
        return MemoryCandidateProposal(
            memory_type="ROUTINE",
            normalized_content=content,
            confirmation_question=f"要記住您{content.rstrip('。')}嗎？",
            confidence_band="HIGH",
            extractor_version=EXTRACTOR_VERSION,
        )
