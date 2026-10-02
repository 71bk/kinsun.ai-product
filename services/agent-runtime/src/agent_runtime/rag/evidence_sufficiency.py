"""Opt-in reviewed evidence decisions; ranking and AI anchors are not approval."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, model_validator

from agent_runtime.rag.citations import append_citations
from agent_runtime.rag.filters import is_normal_rag_eligible
from agent_runtime.rag.models import RetrievalResultV2

EvidenceStatus = Literal["SUFFICIENT", "INSUFFICIENT", "UNKNOWN", "CLARIFY", "FAILED"]
FALLBACK = "目前資料尚未完整支持這個問題，為避免推測，本次不產生知識庫回答。"


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EvidenceRequest(EvidenceModel):
    request_id: str
    query: str
    role: str
    purpose: str
    release_id: str
    policy_sha256: str
    runtime_policy_sha256: str
    query_profile: Literal["natural_language", "legal"] = "natural_language"
    scope_id: str | None = None
    clarified_facets: tuple[str, ...] = ()


class ReviewedClaim(EvidenceModel):
    claim_id: str
    text: str = Field(min_length=1)
    qualifiers: tuple[str, ...]
    facets: tuple[str, ...]


class SupportMember(EvidenceModel):
    search_chunk_id: str
    citation_chunk_id: str
    source_id: str
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SupportSet(EvidenceModel):
    set_id: str
    members: tuple[SupportMember, ...] = Field(min_length=1)
    claim_ids: tuple[str, ...] = Field(min_length=1)
    facets: tuple[str, ...] = Field(min_length=1)


class ReviewedScope(EvidenceModel):
    scope_id: str
    queries: tuple[str, ...] = Field(min_length=1)
    roles: tuple[str, ...] = Field(min_length=1)
    purposes: tuple[str, ...] = Field(min_length=1)
    topic: Literal["application", "service_code"]
    required_facets: tuple[str, ...] = Field(min_length=1)
    clarification_facets: tuple[str, ...] = ()
    claims: tuple[ReviewedClaim, ...] = Field(min_length=1)
    support_sets: tuple[SupportSet, ...] = Field(min_length=1)
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    review_status: Literal["REVIEWED", "PENDING"]


class EvidencePolicy(EvidenceModel):
    policy_id: str
    release_id: str
    runtime_policy_sha256: str
    review_status: Literal["REVIEWED", "PENDING"]
    usage: Literal["REVIEWED_RUNTIME", "SYNTHETIC_TEST_ONLY"]
    scopes: tuple[ReviewedScope, ...]


class EvidenceCandidate(EvidenceModel):
    request_id: str
    search_chunk_id: str
    release_id: str
    runtime_policy_sha256: str
    result: RetrievalResultV2
    live_source: dict[str, object]


class EvidenceDecision(EvidenceModel):
    request_id: str
    status: EvidenceStatus
    reason_codes: tuple[str, ...]
    selected_candidates: tuple[EvidenceCandidate, ...] = ()
    claims: tuple[ReviewedClaim, ...] = ()

    @model_validator(mode="after")
    def partial_evidence_is_private(self) -> EvidenceDecision:
        if self.status != "SUFFICIENT" and (self.selected_candidates or self.claims):
            raise ValueError("partial evidence cannot leave evaluator")
        if self.status == "SUFFICIENT" and (
            not self.claims or not 1 <= len(self.selected_candidates) <= 5
        ):
            raise ValueError("sufficient evidence must be complete and bounded")
        return self


class EvidenceSufficiencyEvaluator:
    def __init__(
        self, policy: EvidencePolicy, policy_sha256: str, *, synthetic_mode: bool = False
    ) -> None:
        self.policy = policy
        self.policy_sha256 = policy_sha256
        self.synthetic_mode = synthetic_mode

    def evaluate(
        self,
        request: EvidenceRequest,
        candidates: Sequence[EvidenceCandidate],
        *,
        now: datetime | None = None,
    ) -> EvidenceDecision:
        def deny(status: EvidenceStatus, reason: str) -> EvidenceDecision:
            return EvidenceDecision(
                request_id=request.request_id, status=status, reason_codes=(reason,)
            )

        policy = self.policy
        if policy.review_status != "REVIEWED" or (
            policy.usage == "SYNTHETIC_TEST_ONLY" and not self.synthetic_mode
        ):
            return deny("UNKNOWN", "POLICY_NOT_REVIEWED")
        if (
            request.policy_sha256 != self.policy_sha256
            or request.release_id != policy.release_id
            or request.runtime_policy_sha256 != policy.runtime_policy_sha256
        ):
            return deny("UNKNOWN", "POLICY_BINDING_MISMATCH")
        if request.purpose == "legal_reference" and request.query_profile != "legal":
            return deny("UNKNOWN", "PURPOSE_PROFILE_MISMATCH")
        scopes = [s for s in policy.scopes if s.scope_id == request.scope_id]
        if len(scopes) != 1:
            return deny("UNKNOWN", "UNKNOWN_SCOPE")
        scope = scopes[0]
        if scope.review_status != "REVIEWED":
            return deny("UNKNOWN", "SCOPE_NOT_REVIEWED")
        if (
            request.query not in scope.queries
            or request.role not in scope.roles
            or request.purpose not in scope.purposes
        ):
            return deny("UNKNOWN", "REQUEST_SCOPE_MISMATCH")
        at = now or datetime.now(UTC)
        if at.tzinfo is None or not scope.valid_from <= at < scope.valid_until:
            return deny("UNKNOWN", "SCOPE_EXPIRED")
        if not set(scope.clarification_facets) <= set(request.clarified_facets):
            return deny("CLARIFY", "CLARIFICATION_REQUIRED")
        if len(candidates) > 5:
            return deny("INSUFFICIENT", "CANDIDATE_LIMIT")
        by_id = {c.search_chunk_id: c for c in candidates}
        claims = {c.claim_id: c for c in scope.claims}
        if (
            len(by_id) != len(candidates)
            or len({c.result.chunk_id for c in candidates}) != len(candidates)
            or len(claims) != len(scope.claims)
        ):
            return deny("UNKNOWN", "DUPLICATE_BINDING")
        for support in scope.support_sets:
            # A support set is atomic: never truncate a six-member set to five.
            if (
                len(support.members) > 5
                or len({m.search_chunk_id for m in support.members}) != len(support.members)
                or len({m.citation_chunk_id for m in support.members}) != len(support.members)
            ):
                continue
            if set(support.claim_ids) != set(claims) or not set(scope.required_facets) <= set(
                support.facets
            ):
                continue
            if not set(scope.required_facets) <= {
                f for claim in claims.values() for f in claim.facets
            }:
                continue
            selected = []
            for member in support.members:
                candidate = by_id.get(member.search_chunk_id)
                if candidate is None or not self._bound(request, candidate, member):
                    break
                selected.append(candidate)
            else:
                return EvidenceDecision(
                    request_id=request.request_id,
                    status="SUFFICIENT",
                    reason_codes=("COMPLETE_REVIEWED_SUPPORT",),
                    selected_candidates=tuple(selected),
                    claims=scope.claims,
                )
        return deny("INSUFFICIENT", "NO_COMPLETE_SUPPORT_SET")

    def _bound(
        self, request: EvidenceRequest, candidate: EvidenceCandidate, member: SupportMember
    ) -> bool:
        result, source = candidate.result, candidate.live_source
        try:
            RetrievalResultV2.model_validate(result.model_dump())
        except (ValidationError, ValueError):
            return False
        if (
            candidate.request_id != request.request_id
            or candidate.runtime_policy_sha256 != request.runtime_policy_sha256
            or candidate.release_id != request.release_id
            or source.get("chunk_id") != candidate.search_chunk_id
            or source.get("source_id") != member.source_id
        ):
            return False
        if result.chunk_id != member.citation_chunk_id or result.source_id != member.source_id:
            return False
        if (
            source.get("text") != result.text
            or sha256(result.text.encode()).hexdigest() != member.text_sha256
        ):
            return False
        if (
            result.review_status != "verified"
            or source.get("review_status") != "verified"
            or source.get("production_approved") != result.production_approved
        ):
            return False
        if not is_normal_rag_eligible(
            source,
            request.query_profile,
            audience=request.role,
            purpose=request.purpose,
            governed_citations=True,
            allow_needs_review=self.synthetic_mode,
        ):
            return False
        return result.requires_official_assessment == source.get(
            "requires_official_assessment"
        ) and result.requires_professional_assessment == source.get(
            "requires_professional_assessment"
        )


def render(decision: EvidenceDecision) -> str:
    """Render reviewed claims and qualifiers verbatim, with no model or truncation."""
    if decision.status != "SUFFICIENT":
        return FALLBACK
    if not decision.claims or not 1 <= len(decision.selected_candidates) <= 5:
        raise ValueError("incomplete evidence decision")
    body = "\n\n".join("\n".join((claim.text, *claim.qualifiers)) for claim in decision.claims)
    answer = append_citations(body, [c.result for c in decision.selected_candidates])
    if not answer.startswith(body + "\n\n"):
        raise ValueError("controlled answer exceeds contract; refusing truncation")
    return answer
