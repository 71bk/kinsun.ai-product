from agent_runtime.contracts.models import SafetyEvaluation


def fallback_reply(safety_result: SafetyEvaluation, original_reply: str) -> str:
    if safety_result.safe_reply:
        return safety_result.safe_reply
    return original_reply
