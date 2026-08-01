from agent_runtime.common.enums import ResultStatus, SafetyDecision
from agent_runtime.contracts.models import SafetyEvaluation

# `is_terminal_decision()` was removed with the fake orchestrator loop. It read
# `decision != ALLOW`, which is backwards for a stop condition — ALLOW is the
# success terminal state. Whatever replaces it must arrive with the multi-step
# loop that actually needs it, so the semantics can be defined against a real
# remediation path rather than guessed.


def map_to_status(safety_result: SafetyEvaluation) -> ResultStatus:
    if safety_result.decision == SafetyDecision.ALLOW:
        return ResultStatus.SUCCESS
    if safety_result.decision in (SafetyDecision.SAFE_FALLBACK, SafetyDecision.HUMAN_REVIEW):
        return ResultStatus.SAFE_FALLBACK
    return ResultStatus.BLOCKED
