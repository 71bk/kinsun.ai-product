from pydantic import Field

from agent_runtime.contracts.models import (
    ContractBaseModel,
    RiskLevelField,
    SafetyDecisionField,
    SafetyEvaluation,
)


class SafetyEvaluationResult(ContractBaseModel):
    decision: SafetyDecisionField
    risk_level: RiskLevelField
    reason_codes: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)
    safe_reply: str | None = None

    def to_contract(self) -> SafetyEvaluation:
        return SafetyEvaluation(
            schema_version=SafetyEvaluation.model_fields["schema_version"].default,
            decision=self.decision,
            risk_level=self.risk_level,
            reason_codes=self.reason_codes,
            matched_terms=self.matched_terms,
            safe_reply=self.safe_reply,
        )
