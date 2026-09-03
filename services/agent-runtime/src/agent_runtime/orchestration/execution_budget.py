from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from agent_runtime.common.errors import StepLimitError

T = TypeVar("T")


@dataclass(slots=True)
class ExecutionBudget:
    """One monotonic deadline plus explicit decision and future Tool counters."""

    latency_budget_ms: int
    max_decisions: int
    max_tool_rounds: int
    max_total_tools: int
    decision_count: int = 0
    tool_round_count: int = 0
    total_tool_count: int = 0
    _deadline: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.latency_budget_ms < 1:
            raise ValueError("latency_budget_ms must be positive")
        if self.max_decisions < 1:
            raise ValueError("max_decisions must be positive")
        if self.max_tool_rounds < 0 or self.max_total_tools < 0:
            raise ValueError("Tool limits must not be negative")
        self._deadline = time.monotonic() + self.latency_budget_ms / 1000

    def consume_decision(self) -> int:
        if self.decision_count >= self.max_decisions:
            raise StepLimitError("Agent decision budget exhausted")
        self.decision_count += 1
        return self.decision_count

    def consume_tool_round(self, tool_count: int) -> None:
        """Reserve an entire Tool round atomically before any Tool call starts."""

        if tool_count < 1:
            raise ValueError("tool_count must be positive")
        if self.tool_round_count >= self.max_tool_rounds:
            raise StepLimitError("Agent Tool round budget exhausted")
        if self.total_tool_count + tool_count > self.max_total_tools:
            raise StepLimitError("Agent total Tool budget exhausted")
        self.tool_round_count += 1
        self.total_tool_count += tool_count

    def remaining_seconds(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Agent latency budget exhausted")
        return remaining

    async def wait_for(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Apply the same end-to-end deadline to the next external await."""

        timeout = self.remaining_seconds()
        return await asyncio.wait_for(operation(), timeout=timeout)
