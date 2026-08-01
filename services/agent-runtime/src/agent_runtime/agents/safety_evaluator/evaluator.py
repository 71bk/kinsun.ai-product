import re

from agent_runtime.agents.safety_evaluator.models import SafetyEvaluationResult
from agent_runtime.common.enums import RiskLevel, SafetyDecision
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest, SafetyEvaluation


class SafetyEvaluator:
    """Deterministic safety rules for M0 foundation."""

    HIGH_RISK_PATTERNS = [
        r"停藥",
        r"改藥",
        r"自行.*藥",
        r"停用",
        r"用藥建議",
        r"診斷",
    ]

    def evaluate(self, request: AgentRunRequest, candidate_reply: str) -> SafetyEvaluation:
        text = f"{request.input_text} {candidate_reply}"
        matched = []
        for pattern in self.HIGH_RISK_PATTERNS:
            if re.search(pattern, text):
                matched.append(pattern)

        if matched:
            return SafetyEvaluation(
                schema_version=SafetyEvaluation.model_fields["schema_version"].default,
                decision=SafetyDecision.BLOCK,
                risk_level=RiskLevel.HIGH,
                reason_codes=["HIGH_RISK_REQUEST"],
                matched_terms=matched,
                safe_reply="我不能提供醫療建議，請先與照護人員或醫師確認，避免風險。",
            )

        fallback = SafetyEvaluationResult(
            decision=SafetyDecision.ALLOW,
            risk_level=RiskLevel.LOW,
            reason_codes=["ALLOW"],
        )

        return fallback.to_contract()

    def evaluate_context(self, context_manifest: ContextManifest) -> bool:
        return bool(context_manifest.items)
