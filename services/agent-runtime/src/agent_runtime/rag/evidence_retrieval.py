"""Injectable opt-in evidence adapter; intentionally has no model dependency."""

from collections.abc import Awaitable, Callable, Sequence

from agent_runtime.rag.evidence_sufficiency import (
    EvidenceCandidate,
    EvidenceDecision,
    EvidenceRequest,
    EvidenceSufficiencyEvaluator,
)

CandidateLoader = Callable[[EvidenceRequest], Awaitable[Sequence[EvidenceCandidate]]]


class EvidenceRetriever:
    def __init__(
        self,
        candidate_loader: CandidateLoader,
        evaluator: EvidenceSufficiencyEvaluator,
        *,
        enabled: bool = False,
    ) -> None:
        self.candidate_loader = candidate_loader
        self.evaluator = evaluator
        self.enabled = enabled

    async def retrieve_evidence(self, request: EvidenceRequest) -> EvidenceDecision:
        if not self.enabled:
            return EvidenceDecision(
                request_id=request.request_id, status="UNKNOWN", reason_codes=("V3_DISABLED",)
            )
        # Reject unknown policy/scope before embeddings or search.
        preliminary = self.evaluator.evaluate(request, ())
        if preliminary.status in {"UNKNOWN", "CLARIFY"}:
            return preliminary
        try:
            candidates = await self.candidate_loader(request)
            return self.evaluator.evaluate(request, candidates)
        except Exception:
            return EvidenceDecision(
                request_id=request.request_id,
                status="FAILED",
                reason_codes=("EVIDENCE_UNAVAILABLE",),
            )
