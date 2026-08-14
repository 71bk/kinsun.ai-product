import re

from agent_runtime.agents.safety_evaluator.models import SafetyEvaluationResult
from agent_runtime.common.enums import RiskLevel, SafetyDecision
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest, SafetyEvaluation


class SafetyEvaluator:
    """Deterministic safety rules for M0 foundation."""

    HIGH_RISK_REQUEST_PATTERNS = [
        r"停藥",
        r"改藥",
        r"自行.*藥",
        r"停用",
        r"用藥建議",
        r"診斷",
    ]
    UNSAFE_REPLY_PATTERNS = [
        r"(?:可能|應該|大概|會不會)是.{0,20}(?:造成|引起|因為|沒睡好|太累)",
        r"(?:先|可以|建議|不妨).{0,16}(?:喝水|喝點|吃|服用|休息|熱敷|冰敷|停藥|改藥)",
    ]

    def evaluate(self, request: AgentRunRequest, candidate_reply: str) -> SafetyEvaluation:
        request_matches = [
            pattern
            for pattern in self.HIGH_RISK_REQUEST_PATTERNS
            if re.search(pattern, request.input_text)
        ]
        reply_matches = [
            pattern for pattern in self.UNSAFE_REPLY_PATTERNS if re.search(pattern, candidate_reply)
        ]
        matched = request_matches + reply_matches

        if matched:
            return SafetyEvaluation(
                schema_version=SafetyEvaluation.model_fields["schema_version"].default,
                decision=SafetyDecision.BLOCK,
                risk_level=RiskLevel.HIGH,
                reason_codes=[
                    "UNSAFE_MEDICAL_REPLY" if reply_matches else "HIGH_RISK_REQUEST"
                ],
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
