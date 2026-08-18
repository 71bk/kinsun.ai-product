"""Deterministic final gate for memory entering private Agent context."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from app.policies.memory_policy import (
    CONFIRMABLE_MEMORY_KINDS,
    CURRENT_MEMORY_POLICY_VERSION,
    LOW_MEMORY_KINDS,
    TRUSTED_SPEAKER_LEVELS,
)

_CONFIRMATION_METHODS = {"ELDER_UI", "ELDER_VOICE", "WITNESSED_VOICE"}
CURRENT_MEMORY_EVIDENCE_STATE = "CURRENT"
LEGACY_MEMORY_EVIDENCE_STATE = "LEGACY_NEEDS_REVIEW"


def memory_content_digest(content: str) -> str:
    """Return the canonical lowercase SHA-256 digest for normalized content."""
    return sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryTrustEvidence:
    evidence_state: str
    version: int
    content: str
    content_digest: str | None
    memory_kind: str | None
    consent_id_present: bool
    policy_version: str | None
    policy_decision: str | None
    actual_risk_level: str | None
    verification_level: str | None
    required_verification: str | None
    speaker_verification_level: str | None
    speaker_evidence_reference: str | None
    confirmed_version: int | None
    confirmed_content_digest: str | None
    confirmation_method: str | None
    confirmation_evidence_reference: str | None
    confirmed_by_present: bool
    confirmed_at_present: bool
    confirmation_record_present: bool
    decision_support_mode: str = "STANDARD"
    decision_support_binding_current: bool = True


@dataclass(frozen=True)
class MemoryTrustDecision:
    allowed: bool
    reason_code: str


def evaluate_memory_trust(
    evidence: MemoryTrustEvidence,
    *,
    current_policy_version: str = CURRENT_MEMORY_POLICY_VERSION,
    allow_auto_low_risk_memory: bool = False,
) -> MemoryTrustDecision:
    """Apply the Spec 18 evidence gate without consulting model output."""
    if evidence.evidence_state != CURRENT_MEMORY_EVIDENCE_STATE:
        return MemoryTrustDecision(False, LEGACY_MEMORY_EVIDENCE_STATE)
    required_values = (
        evidence.content_digest,
        evidence.memory_kind,
        evidence.policy_version,
        evidence.policy_decision,
        evidence.actual_risk_level,
        evidence.verification_level,
        evidence.required_verification,
        evidence.speaker_verification_level,
    )
    if not evidence.consent_id_present or any(value is None for value in required_values):
        return MemoryTrustDecision(False, "LEGACY_EVIDENCE_MISSING")
    if evidence.policy_version != current_policy_version:
        return MemoryTrustDecision(False, "POLICY_VERSION_STALE")
    if evidence.content_digest != memory_content_digest(evidence.content):
        return MemoryTrustDecision(False, "CONTENT_DIGEST_MISMATCH")
    if (
        evidence.speaker_verification_level not in TRUSTED_SPEAKER_LEVELS
        or not evidence.speaker_evidence_reference
    ):
        return MemoryTrustDecision(False, "SPEAKER_EVIDENCE_INVALID")
    if not evidence.decision_support_binding_current:
        return MemoryTrustDecision(False, "DECISION_SUPPORT_PROFILE_STALE")
    if evidence.decision_support_mode == "REPRESENTATIVE_REQUIRED":
        return MemoryTrustDecision(False, "REPRESENTATIVE_REQUIRED_NO_ELDER_MEMORY")
    if evidence.decision_support_mode not in {"STANDARD", "SUPPORTED"}:
        return MemoryTrustDecision(False, "DECISION_SUPPORT_PROFILE_INVALID")

    if evidence.actual_risk_level == "LOW":
        if (
            evidence.memory_kind in LOW_MEMORY_KINDS
            and evidence.policy_decision == "AUTO_ACTIVATED_LOW"
            and evidence.verification_level == "POLICY_VERIFIED"
            and evidence.required_verification == "NONE"
            and evidence.decision_support_mode == "STANDARD"
        ):
            if not allow_auto_low_risk_memory:
                return MemoryTrustDecision(False, "AUTO_LOW_RISK_MEMORY_DISABLED")
            return MemoryTrustDecision(True, "TRUSTED_LOW")
        if (
            evidence.memory_kind in LOW_MEMORY_KINDS
            and evidence.policy_decision == "ELDER_CONFIRMED_SUPPORTED"
            and evidence.verification_level == "ELDER_CONFIRMED"
            and evidence.required_verification == "SUPPORTED_ELDER_CONFIRMATION"
            and evidence.decision_support_mode == "SUPPORTED"
        ):
            return _evaluate_confirmation_evidence(evidence, "TRUSTED_SUPPORTED_LOW")
        return MemoryTrustDecision(False, "LOW_POLICY_EVIDENCE_INVALID")

    if evidence.actual_risk_level == "MEDIUM":
        standard_confirmation = (
            evidence.memory_kind not in CONFIRMABLE_MEMORY_KINDS
            or evidence.policy_decision != "ELDER_CONFIRMED_MEDIUM"
            or evidence.required_verification != "ELDER_CONFIRMATION"
            or evidence.decision_support_mode != "STANDARD"
        )
        supported_confirmation = (
            evidence.memory_kind not in CONFIRMABLE_MEMORY_KINDS
            or evidence.policy_decision != "ELDER_CONFIRMED_SUPPORTED"
            or evidence.required_verification != "SUPPORTED_ELDER_CONFIRMATION"
            or evidence.decision_support_mode != "SUPPORTED"
        )
        if evidence.verification_level != "ELDER_CONFIRMED" or (
            standard_confirmation and supported_confirmation
        ):
            return MemoryTrustDecision(False, "MEDIUM_CONFIRMATION_REQUIRED")
        return _evaluate_confirmation_evidence(evidence, "TRUSTED_MEDIUM")

    return MemoryTrustDecision(False, "HIGH_OR_UNKNOWN_RISK")


def _evaluate_confirmation_evidence(
    evidence: MemoryTrustEvidence,
    trusted_reason_code: str,
) -> MemoryTrustDecision:
    if (
        evidence.confirmed_version != evidence.version
        or evidence.confirmed_content_digest != evidence.content_digest
    ):
        return MemoryTrustDecision(False, "CONFIRMATION_VERSION_STALE")
    if not evidence.confirmation_record_present:
        return MemoryTrustDecision(False, "CONFIRMATION_RECORD_MISSING")
    if (
        evidence.confirmation_method not in _CONFIRMATION_METHODS
        or not evidence.confirmation_evidence_reference
        or not evidence.confirmed_by_present
        or not evidence.confirmed_at_present
    ):
        return MemoryTrustDecision(False, "CONFIRMATION_EVIDENCE_INVALID")
    return MemoryTrustDecision(True, trusted_reason_code)
