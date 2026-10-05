"""Minimize the private V3 response before it crosses the family boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.public_knowledge import PublicKnowledgeAnswer, PublicKnowledgeSource


class _Source(BaseModel):
    # V3 also contains full public excerpts and provenance. They stay private to
    # the adapter; only the explicit PublicKnowledgeSource projection is returned.
    model_config = ConfigDict(extra="ignore", strict=True)
    chunk_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=512)
    source_locator: str = Field(min_length=1, max_length=2048)
    is_official_source: Literal[True]
    official_source_page_url: str | None
    direct_official_source_url: str | None
    current_status: Literal["current", "unknown"]

    def public_source(self) -> PublicKnowledgeSource:
        return PublicKnowledgeSource(
            title=self.title,
            url=self.official_source_page_url or self.direct_official_source_url or "",
            locator=self.source_locator,
            current_status=self.current_status,
        )


class _Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["3.0.0"]
    request_id: str = Field(min_length=2, max_length=128)
    status: Literal["SUCCESS", "NO_DATA", "FAILED"]
    decision: Literal["SUFFICIENT", "PARTIAL", "INSUFFICIENT", "UNKNOWN", "CLARIFY", "FAILED"]
    fallback_message: str | None = Field(max_length=1000)
    answer_text: str | None = Field(max_length=50000)
    results: list[_Source] = Field(max_length=5)
    reason_codes: list[str] = Field(default_factory=list, max_length=32)
    missing_facets: list[str] = Field(default_factory=list, max_length=100)
    release_id: str | None = Field(default=None, max_length=128)
    embedding_profile_id: str | None = Field(default=None, max_length=128)
    policy_version: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "SUCCESS":
            if (
                self.decision not in {"SUFFICIENT", "PARTIAL"}
                or not self.results
                or not self.answer_text
                or self.fallback_message is not None
                or not all((self.release_id, self.embedding_profile_id, self.policy_version))
                or len({source.chunk_id for source in self.results}) != len(self.results)
                or bool(self.missing_facets) != (self.decision == "PARTIAL")
            ):
                raise ValueError("Inconsistent evidence answer")
        elif (
            self.results
            or self.answer_text is not None
            or not self.fallback_message
            or (self.status == "FAILED" and self.decision != "FAILED")
            or (
                self.status == "NO_DATA"
                and self.decision not in {"INSUFFICIENT", "UNKNOWN", "CLARIFY"}
            )
        ):
            raise ValueError("Inconsistent evidence fallback")
        return self


class _Meta(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    correlation_id: str
    timestamp: str
    schema_version: Literal["1.0"]


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    data: _Evidence
    meta: _Meta


def unavailable_answer(language: str) -> PublicKnowledgeAnswer:
    return PublicKnowledgeAnswer(
        status="UNAVAILABLE",
        answer=(
            "The knowledge service could not complete your answer. Please try again later."
            if language == "en-US"
            else "問答服務暫時無法完成回答，請稍後再試。"
        ),
    )


def public_answer(payload: object, *, request_id: str, correlation_id: str, language: str):
    envelope = _Envelope.model_validate(payload)
    evidence = envelope.data
    if evidence.request_id != request_id or envelope.meta.correlation_id != correlation_id:
        raise ValueError("Evidence response binding mismatch")
    if evidence.status == "FAILED":
        return unavailable_answer(language)
    if evidence.status == "NO_DATA":
        status = (
            "BLOCKED"
            if "SAFETY_GATE" in evidence.reason_codes
            else "CLARIFY"
            if evidence.decision == "CLARIFY"
            else "NO_DATA"
        )
        # Do not forward arbitrary upstream fallback/error text to families.
        messages = {
            "BLOCKED": (
                "目前無法安全回答這個問題。涉及醫療或照護決策時，請先與照護人員或醫師確認。",
                "This question cannot be answered safely. "
                "For medical or care decisions, please consult a care professional or doctor.",
            ),
            "CLARIFY": (
                "請再說明您想了解的服務、規定或申請步驟。",
                "Please clarify the service, rule or application step you want to know about.",
            ),
            "NO_DATA": (
                "目前找到的資料不足以回答，請補充您想了解的服務或問題細節。",
                "There is not enough information to answer. "
                "Please add details about the service or question.",
            ),
        }
        return PublicKnowledgeAnswer(status=status, answer=messages[status][language == "en-US"])
    body, separator, _ = (evidence.answer_text or "").rpartition("\n\n引用來源：\n")
    return PublicKnowledgeAnswer(
        status="PARTIAL" if evidence.decision == "PARTIAL" else "ANSWER",
        answer=(body if separator else evidence.answer_text or "").strip(),
        sources=[source.public_source() for source in evidence.results],
    )
