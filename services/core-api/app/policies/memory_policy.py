"""Deterministic Core-owned policy for long-term memory proposals."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

CURRENT_MEMORY_POLICY_VERSION = "memory-policy-2026-08-18.v1"

LOW_MEMORY_KINDS = frozenset({"MUSIC_PREFERENCE", "HOBBY", "PREFERRED_ADDRESS"})
MEDIUM_MEMORY_KINDS = frozenset({"FAMILY_RELATIONSHIP", "CONTACT_ROUTINE", "DAILY_ROUTINE"})
CONFIRMABLE_MEMORY_KINDS = LOW_MEMORY_KINDS | MEDIUM_MEMORY_KINDS
HIGH_MEMORY_KINDS = frozenset(
    {
        "HEALTH_INFERENCE",
        "MEDICATION_JUDGMENT",
        "MOOD_OR_LONELINESS_INFERENCE",
        "FAMILY_CONFLICT",
        "FINANCIAL_INFORMATION",
        "SENSITIVE_OR_UNKNOWN",
    }
)

MIN_CANDIDATE_CONFIDENCE = 0.70
LOW_AUTO_ACTIVATION_CONFIDENCE = 0.85
TRUSTED_SPEAKER_LEVELS = frozenset({"VERIFIED_ELDER", "WITNESSED_ELDER"})

_MEMORY_KIND_TYPES = {
    "MUSIC_PREFERENCE": "PREFERENCE",
    "HOBBY": "PREFERENCE",
    "PREFERRED_ADDRESS": "COMMUNICATION_PREFERENCE",
    "FAMILY_RELATIONSHIP": "IMPORTANT_RELATIONSHIP",
    "CONTACT_ROUTINE": "ROUTINE",
    "DAILY_ROUTINE": "ROUTINE",
}
_LOW_KIND_MARKERS = {
    "MUSIC_PREFERENCE": ("音樂", "歌曲", "聽歌", "歌仔戲", "戲曲", "music", "song"),
    "HOBBY": ("喜歡", "興趣", "愛好", "嗜好", "hobby", "enjoy"),
    "PREFERRED_ADDRESS": ("稱呼", "叫我", "名字", "address me", "call me"),
}
_SENSITIVE_CONTENT_TERMS = (
    "藥",
    "病",
    "醫院",
    "醫生",
    "吃藥",
    "用藥",
    "藥物",
    "藥名",
    "劑量",
    "血壓",
    "血糖",
    "糖尿病",
    "失智",
    "認知障礙",
    "診斷",
    "疾病",
    "住院",
    "疼痛",
    "孤單",
    "寂寞",
    "憂鬱",
    "不想活",
    "吵架",
    "衝突",
    "虐待",
    "銀行",
    "帳戶",
    "存款",
    "財產",
    "債務",
    "提款",
    "密碼",
    "medication",
    "diagnosis",
    "dementia",
    "diabetes",
    "blood pressure",
    "health",
    "doctor",
    "hospital",
    "money",
    "password",
    "bank account",
    "debt",
)


@dataclass(frozen=True)
class SourceSpeakerEvidence:
    """Core-authored ownership evidence for a source statement."""

    verification_level: str
    evidence_reference: str | None
    speaker_role: str | None
    speaker_actor_id: UUID | None
    verification_method: str


@dataclass(frozen=True)
class MemoryCandidatePolicyDecision:
    """A bounded policy result; Agent hints are deliberately absent."""

    create_memory: bool
    status: str | None
    actual_risk_level: str
    policy_decision: str
    verification_level: str
    required_verification: str
    reason_code: str


def derive_turn_speaker_evidence(
    *,
    input_mode: str,
    actor_role: str,
    actor_id: UUID,
    session_id: UUID,
    turn_reference: str,
) -> SourceSpeakerEvidence:
    """Derive statement ownership after the caller authorizes the elder scope.

    An authenticated elder text turn binds the statement to the elder account.
    An authenticated non-elder text turn remains third-party. Voice remains
    UNKNOWN until candidate-specific speaker verification is implemented.
    """
    if input_mode == "text":
        level = "VERIFIED_ELDER" if actor_role == "ELDER" else "THIRD_PARTY"
        return SourceSpeakerEvidence(
            verification_level=level,
            evidence_reference=(
                f"conversation-session:{session_id}:turn:{turn_reference}:authenticated-text"
            ),
            speaker_role=actor_role,
            speaker_actor_id=actor_id,
            verification_method="AUTHENTICATED_TEXT",
        )
    return SourceSpeakerEvidence(
        verification_level="UNKNOWN",
        evidence_reference=None,
        speaker_role=None,
        speaker_actor_id=None,
        verification_method="UNVERIFIED_VOICE",
    )


def evaluate_memory_candidate(
    *,
    memory_type: str,
    memory_kind: str,
    normalized_content: str,
    confirmation_question: str,
    extraction_confidence: float,
    possible_conflict: bool,
    speaker_verification_level: str,
    speaker_evidence_reference: str | None,
) -> MemoryCandidatePolicyDecision:
    """Classify a proposal without trusting Agent-provided risk hints."""
    risk_text = f"{normalized_content}\n{confirmation_question}".casefold()
    if (
        memory_kind in HIGH_MEMORY_KINDS
        or memory_kind not in CONFIRMABLE_MEMORY_KINDS
        or any(term in risk_text for term in _SENSITIVE_CONTENT_TERMS)
    ):
        return MemoryCandidatePolicyDecision(
            create_memory=False,
            status=None,
            actual_risk_level="HIGH",
            policy_decision="REJECTED_HIGH_RISK",
            verification_level="UNVERIFIED",
            required_verification="RESTRICTED",
            reason_code="HIGH_RISK_MEMORY_PROHIBITED",
        )
    if _MEMORY_KIND_TYPES.get(memory_kind) != memory_type:
        return MemoryCandidatePolicyDecision(
            create_memory=False,
            status=None,
            actual_risk_level="MEDIUM",
            policy_decision="NO_MEMORY",
            verification_level="UNVERIFIED",
            required_verification="RESTRICTED",
            reason_code="MEMORY_KIND_TYPE_MISMATCH",
        )
    if speaker_verification_level not in TRUSTED_SPEAKER_LEVELS or not speaker_evidence_reference:
        return MemoryCandidatePolicyDecision(
            create_memory=False,
            status=None,
            actual_risk_level=("LOW" if memory_kind in LOW_MEMORY_KINDS else "MEDIUM"),
            policy_decision="NO_MEMORY",
            verification_level="UNVERIFIED",
            required_verification="RESTRICTED",
            reason_code="SPEAKER_OWNERSHIP_UNVERIFIED",
        )
    if possible_conflict:
        return MemoryCandidatePolicyDecision(
            create_memory=False,
            status=None,
            actual_risk_level="MEDIUM",
            policy_decision="NO_MEMORY",
            verification_level="UNVERIFIED",
            required_verification="RESTRICTED",
            reason_code="CONFLICT_REVIEW_REQUIRED",
        )
    if extraction_confidence < MIN_CANDIDATE_CONFIDENCE:
        return MemoryCandidatePolicyDecision(
            create_memory=False,
            status=None,
            actual_risk_level=("LOW" if memory_kind in LOW_MEMORY_KINDS else "MEDIUM"),
            policy_decision="NO_MEMORY",
            verification_level="UNVERIFIED",
            required_verification="RESTRICTED",
            reason_code="EXTRACTION_CONFIDENCE_TOO_LOW",
        )
    low_semantics_match = any(
        marker in risk_text for marker in _LOW_KIND_MARKERS.get(memory_kind, ())
    )
    if (
        memory_kind in LOW_MEMORY_KINDS
        and extraction_confidence >= LOW_AUTO_ACTIVATION_CONFIDENCE
        and low_semantics_match
    ):
        return MemoryCandidatePolicyDecision(
            create_memory=True,
            status="ACTIVE",
            actual_risk_level="LOW",
            policy_decision="AUTO_ACTIVATED_LOW",
            verification_level="POLICY_VERIFIED",
            required_verification="NONE",
            reason_code="LOW_ALL_OF_SATISFIED",
        )
    return MemoryCandidatePolicyDecision(
        create_memory=True,
        status="PENDING_CONFIRMATION",
        actual_risk_level="MEDIUM",
        policy_decision="PENDING_ELDER_CONFIRMATION",
        verification_level="UNVERIFIED",
        required_verification="ELDER_CONFIRMATION",
        reason_code="ELDER_CONFIRMATION_REQUIRED",
    )
