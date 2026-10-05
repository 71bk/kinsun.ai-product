"""Private V3 wire contract for natural public knowledge answers."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from agent_runtime.rag.models import (
    ID_REGEX,
    RagBaseModel,
    RetrievalRequestV2,
    RetrievalResultV2,
    RetrievalStatus,
)

EvidenceStatus = Literal["SUFFICIENT", "INSUFFICIENT", "UNKNOWN", "CLARIFY", "FAILED", "PARTIAL"]
PublicAudience = Literal["elder", "family_caregiver", "care_professional", "system_admin"]


class RetrievalRequestV3(RetrievalRequestV2):
    """Clients supply a question; policy scopes and evidence bindings are server-owned."""

    schema_version: Literal["3.0.0"]
    audience: PublicAudience
    purpose: Literal["general_information", "legal_reference"]

    @model_validator(mode="after")
    def profile_matches_purpose(self) -> RetrievalRequestV3:
        expected = "legal" if self.purpose == "legal_reference" else "natural_language"
        if self.query_profile != expected:
            raise ValueError("query profile must match the evidence purpose")
        return self


class RetrievalResultV3(RetrievalResultV2):
    """V3 exposes source currency without changing the V2 wire contract."""

    current_status: Literal["current", "unknown"]
    is_official_source: Literal[True]
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def warnings_are_nonblank(self) -> RetrievalResultV3:
        if any(not value.strip() or len(value) > 1000 for value in self.warnings):
            raise ValueError("invalid citation warning")
        for value in (
            self.direct_official_source_url,
            self.official_source_page_url,
            self.direct_source_url,
            self.source_page_url,
        ):
            if value is not None:
                parsed = urlsplit(value)
                if parsed.username is not None or parsed.password is not None:
                    raise ValueError("citation URL credentials are forbidden")
        selected = urlsplit(self.source_url)
        if not selected.hostname or not (
            selected.hostname == "gov.tw" or selected.hostname.endswith(".gov.tw")
        ):
            raise ValueError("public knowledge requires an official government source URL")
        return self


class RetrievalResponseV3(RagBaseModel):
    schema_version: Literal["3.0.0"] = "3.0.0"
    request_id: str = Field(min_length=2, max_length=128, pattern=ID_REGEX)
    status: RetrievalStatus
    decision: EvidenceStatus
    fallback_message: str | None = Field(default=None, max_length=1000)
    results: list[RetrievalResultV3] = Field(default_factory=list, max_length=5)
    answer_text: str | None = Field(default=None, min_length=1, max_length=50000)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    release_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"\S")
    embedding_profile_id: str | None = Field(
        default=None, min_length=1, max_length=128, pattern=r"\S"
    )
    policy_version: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"\S")
    missing_facets: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def decision_and_content_agree(self) -> RetrievalResponseV3:
        if any(not code.strip() or len(code) > 128 for code in self.reason_codes):
            raise ValueError("invalid evidence reason code")
        if any(not facet.strip() or len(facet) > 128 for facet in self.missing_facets):
            raise ValueError("invalid missing evidence facet")
        if self.status == "SUCCESS":
            if self.decision not in ("SUFFICIENT", "PARTIAL") or not 1 <= len(self.results) <= 5:
                raise ValueError("success requires sufficient evidence and one to five citations")
            if self.fallback_message is not None or not self.answer_text:
                raise ValueError("success requires a complete controlled answer")
            if self.decision == "SUFFICIENT" and self.missing_facets:
                raise ValueError("sufficient answer cannot have missing facets")
            if self.decision == "PARTIAL" and not self.missing_facets:
                raise ValueError("partial answer requires missing facets")
            if not self.answer_text.strip():
                raise ValueError("answer must not be blank")
            if not all((self.release_id, self.embedding_profile_id, self.policy_version)):
                raise ValueError("success requires complete evidence bindings")
            if len({result.chunk_id for result in self.results}) != len(self.results):
                raise ValueError("duplicate evidence citation")
        else:
            if self.results or self.answer_text is not None:
                raise ValueError("fallback must not expose partial evidence or answers")
            if not self.fallback_message or not self.fallback_message.strip():
                raise ValueError("fallback must be explicit")
            if self.status == "FAILED" and self.decision != "FAILED":
                raise ValueError("provider failure must remain a failure")
            if self.status == "NO_DATA" and self.decision not in (
                "INSUFFICIENT",
                "UNKNOWN",
                "CLARIFY",
            ):
                raise ValueError("no-data response cannot imply supported evidence")
        return self


def evidence_failure(request_id: str) -> RetrievalResponseV3:
    return RetrievalResponseV3(
        request_id=request_id,
        status="FAILED",
        decision="FAILED",
        fallback_message="目前無法取得可驗證的資料，請稍後再試。",
        reason_codes=["EVIDENCE_UNAVAILABLE"],
    )
