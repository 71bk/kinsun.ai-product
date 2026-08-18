"""Deterministic DecisionSupportProfile effects on Memory policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from app.policies.memory_policy import MemoryCandidatePolicyDecision

DECISION_SCOPE_MEMORY_CONFIRMATION = "MEMORY_CONFIRMATION"
DECISION_SUPPORT_MODES = frozenset({"STANDARD", "SUPPORTED", "REPRESENTATIVE_REQUIRED"})
MEMORY_PROFILE_RISKS = frozenset({"LOW", "MEDIUM"})


@dataclass(frozen=True)
class DecisionSupportResolution:
    """Current profile decision for one Elder and Memory data class."""

    usable: bool
    mode: str
    allowed_memory_risks: frozenset[str]
    profile_id: UUID | None
    profile_version: int | None
    data_class: str
    reason_code: str

    @property
    def is_default_standard(self) -> bool:
        return self.usable and self.mode == "STANDARD" and self.profile_id is None


@dataclass(frozen=True)
class ProfiledMemoryPolicyDecision:
    """Candidate policy plus the profile binding that produced it."""

    allowed: bool
    decision: MemoryCandidatePolicyDecision
    profile: DecisionSupportResolution
    reason_code: str


def default_standard_resolution(data_class: str) -> DecisionSupportResolution:
    """Preserve ADR 0014 behavior when no profile has ever been authored."""
    return DecisionSupportResolution(
        usable=True,
        mode="STANDARD",
        allowed_memory_risks=MEMORY_PROFILE_RISKS,
        profile_id=None,
        profile_version=None,
        data_class=data_class,
        reason_code="DEFAULT_STANDARD_NO_PROFILE",
    )


def blocked_resolution(data_class: str, reason_code: str) -> DecisionSupportResolution:
    return DecisionSupportResolution(
        usable=False,
        mode="BLOCKED",
        allowed_memory_risks=frozenset(),
        profile_id=None,
        profile_version=None,
        data_class=data_class,
        reason_code=reason_code,
    )


def apply_decision_support_profile(
    decision: MemoryCandidatePolicyDecision,
    profile: DecisionSupportResolution,
) -> ProfiledMemoryPolicyDecision:
    """Apply only restrictive/profile-routing effects; never lower risk."""
    if not profile.usable:
        return ProfiledMemoryPolicyDecision(False, decision, profile, profile.reason_code)
    if profile.mode == "REPRESENTATIVE_REQUIRED":
        return ProfiledMemoryPolicyDecision(
            False,
            decision,
            profile,
            "REPRESENTATIVE_REQUIRED_NO_ELDER_MEMORY",
        )
    if decision.actual_risk_level not in profile.allowed_memory_risks:
        return ProfiledMemoryPolicyDecision(
            False,
            decision,
            profile,
            "DECISION_SUPPORT_RISK_NOT_ALLOWED",
        )
    if profile.mode == "SUPPORTED":
        supported = replace(
            decision,
            status="PENDING_CONFIRMATION",
            policy_decision="PENDING_SUPPORTED_CONFIRMATION",
            verification_level="UNVERIFIED",
            required_verification="SUPPORTED_ELDER_CONFIRMATION",
            reason_code="SUPPORTED_ELDER_CONFIRMATION_REQUIRED",
        )
        return ProfiledMemoryPolicyDecision(
            True,
            supported,
            profile,
            supported.reason_code,
        )
    if profile.mode != "STANDARD":
        return ProfiledMemoryPolicyDecision(
            False,
            decision,
            profile,
            "DECISION_SUPPORT_MODE_INVALID",
        )
    return ProfiledMemoryPolicyDecision(True, decision, profile, decision.reason_code)


def profile_binding_is_current(
    *,
    bound_profile_id: UUID | None,
    bound_profile_version: int | None,
    current: DecisionSupportResolution,
) -> bool:
    """Require exact current binding; default STANDARD is represented by NULL/NULL."""
    return (
        current.usable
        and current.mode != "REPRESENTATIVE_REQUIRED"
        and bound_profile_id == current.profile_id
        and bound_profile_version == current.profile_version
    )
