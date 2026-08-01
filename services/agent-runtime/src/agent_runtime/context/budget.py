from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudget:
    total_tokens: int = 2048
